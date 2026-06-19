"""Tool ABC contract tests — the new `Config` class attribute and the
`__init__(config)` constructor contract introduced in L3.

Verifies:

* Tool subclasses without a custom `Config` instantiate with no args; the
  `_config` attribute is a `BaseModel` (specifically `_EmptyConfig`).
* Tool subclasses with a custom `Config` honor field defaults when no
  config is passed and accept an explicit `Config` instance.
* Type-mismatched Config values raise Pydantic `ValidationError`.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from the_one.tools.base import POSITIONAL_ARGS_KEY, Tool
from the_one.tools.builtins import _TOOL_CLASSES
from the_one.tools.resolver import _EmptyConfig


class _NoConfigTool(Tool):
    """Tool with the inherited empty Config default."""

    name = "no_config"
    description = "Tool without a custom Config."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class _CustomCfg(BaseModel):
    timeout: int = 30


class _CustomCfgTool(Tool):
    """Tool with a custom Config exposing a default-valued field."""

    name = "custom_config"
    description = "Tool with a custom Config."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    Config = _CustomCfg

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class TestToolDefaultConfig:
    def test_no_args_uses_empty_config(self) -> None:
        tool = _NoConfigTool()
        assert isinstance(tool._config, BaseModel)
        # The default is _EmptyConfig (NOT bare BaseModel — Pydantic v2
        # forbids that).
        assert isinstance(tool._config, _EmptyConfig)

    def test_default_config_dump_is_empty(self) -> None:
        tool = _NoConfigTool()
        assert tool._config.model_dump() == {}


class TestToolCustomConfig:
    def test_no_args_uses_default_field_values(self) -> None:
        tool = _CustomCfgTool()
        assert isinstance(tool._config, _CustomCfg)
        assert tool._config.timeout == 30

    def test_explicit_config_overrides_default(self) -> None:
        cfg = _CustomCfg(timeout=10)
        tool = _CustomCfgTool(cfg)
        assert tool._config.timeout == 10

    def test_explicit_bad_type_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            _CustomCfg(timeout="bad")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# L1b additions — Requires class attr; cross_configs + agent_name __init__
# parameters; defaults preserve back-compat for zero-arg `cls()` callers.
# ---------------------------------------------------------------------------


class _OtherCfg(BaseModel):
    """A second BaseModel used to exercise cross_configs by-type lookup."""


class TestToolL1bWidening:
    def test_requires_default_is_empty_tuple(self) -> None:
        # Default `Requires` must be `()` (immutable) so subclasses can't
        # accidentally mutate the class default.
        assert _NoConfigTool.Requires == ()
        assert isinstance(_NoConfigTool.Requires, tuple)

    def test_zero_arg_keeps_back_compat(self) -> None:
        # Existing `cls()` call sites (introspection path, tests) must
        # continue to work with the new init signature.
        tool = _NoConfigTool()
        assert tool._cross_configs == {}
        assert tool._agent_name is None

    def test_explicit_none_kwargs_match_zero_arg(self) -> None:
        tool = _NoConfigTool(config=None, cross_configs=None, agent_name=None)
        assert tool._cross_configs == {}
        assert tool._agent_name is None

    def test_cross_configs_stored_by_type_key(self) -> None:
        custom = _CustomCfg()
        other = _OtherCfg()
        tool = _NoConfigTool(cross_configs={_CustomCfg: custom, _OtherCfg: other})
        assert tool._cross_configs[_CustomCfg] is custom
        assert tool._cross_configs[_OtherCfg] is other

    def test_agent_name_stored(self) -> None:
        tool = _NoConfigTool(agent_name="alpha")
        assert tool._agent_name == "alpha"

    def test_all_three_kwargs_combined(self) -> None:
        cfg = _CustomCfg(timeout=5)
        other = _OtherCfg()
        tool = _CustomCfgTool(
            config=cfg,
            cross_configs={_OtherCfg: other},
            agent_name="bravo",
        )
        assert tool._config is cfg
        assert tool._cross_configs[_OtherCfg] is other
        assert tool._agent_name == "bravo"


# ---------------------------------------------------------------------------
# M16 F03 L07 (#105) — Tool.bind_positional_args: schema-aware binding of
# recovered positional args (gemma's ``shell("echo …")``) onto named params.
# ---------------------------------------------------------------------------


class _ShellLikeTool(Tool):
    """A tool mirroring ShellTool's parameter shape (command first)."""

    name = "shell_like"
    description = "Shell-like tool for positional-binding tests."
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "cwd": {"type": "string"},
            "timeout": {"type": "integer"},
            "host_access": {"type": "boolean"},
        },
        "required": ["command"],
    }

    async def execute(self, **kwargs: Any) -> str:
        return "ok"


class TestBindPositionalArgs:
    def test_single_positional_binds_to_first_property(self) -> None:
        tool = _ShellLikeTool()
        out = tool.bind_positional_args({POSITIONAL_ARGS_KEY: ["echo hi"]})
        assert out == {"command": "echo hi"}
        assert POSITIONAL_ARGS_KEY not in out

    def test_no_sentinel_is_noop(self) -> None:
        tool = _ShellLikeTool()
        out = tool.bind_positional_args({"command": "x"})
        assert out == {"command": "x"}

    def test_does_not_mutate_input(self) -> None:
        tool = _ShellLikeTool()
        original = {POSITIONAL_ARGS_KEY: ["echo hi"]}
        tool.bind_positional_args(original)
        assert original == {POSITIONAL_ARGS_KEY: ["echo hi"]}

    def test_mixed_positional_and_keyword_keyword_wins(self) -> None:
        tool = _ShellLikeTool()
        # `command` already supplied as a keyword → positional fills the next
        # free declaration-order slot (`cwd`), keyword `command` is preserved.
        out = tool.bind_positional_args(
            {"command": "ls", POSITIONAL_ARGS_KEY: ["/tmp"]}
        )
        assert out == {"command": "ls", "cwd": "/tmp"}

    def test_multiple_positionals_bind_in_declaration_order(self) -> None:
        tool = _ShellLikeTool()
        out = tool.bind_positional_args(
            {POSITIONAL_ARGS_KEY: ["echo hi", "/tmp", 5]}
        )
        assert out == {"command": "echo hi", "cwd": "/tmp", "timeout": 5}

    def test_overflow_leaves_remainder_under_sentinel_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        tool = _ShellLikeTool()
        # 5 positionals, only 4 properties → 1 leftover.
        with caplog.at_level(logging.WARNING):
            out = tool.bind_positional_args(
                {POSITIONAL_ARGS_KEY: ["a", "b", 1, True, "extra"]}
            )
        assert out["command"] == "a"
        assert out["cwd"] == "b"
        assert out["timeout"] == 1
        assert out["host_access"] is True
        assert out[POSITIONAL_ARGS_KEY] == ["extra"]
        assert any("positional" in r.message for r in caplog.records)

    def test_no_properties_tool_leaves_sentinel_untouched(self) -> None:
        tool = _NoConfigTool()  # parameters.properties == {}
        out = tool.bind_positional_args({POSITIONAL_ARGS_KEY: ["echo hi"]})
        assert out == {POSITIONAL_ARGS_KEY: ["echo hi"]}

    def test_real_shell_tool_binds_command(self) -> None:
        from the_one.tools.shell import ShellTool

        out = ShellTool().bind_positional_args(
            {POSITIONAL_ARGS_KEY: ["echo hi"]}
        )
        assert out == {"command": "echo hi"}


class TestBuiltinRequiredFirstAgreesWithDeclarationOrder:
    """DD-C: declaration-order binding only coincides with the documented
    'required-params-first' intent if, for every built-in tool, the
    ``required`` list is exactly the first-N declared properties. This test
    future-proofs against a tool that declares an optional param before a
    required one (which would silently mis-bind positional args)."""

    def test_required_is_prefix_of_declared_properties(self) -> None:
        for name, cls in _TOOL_CLASSES.items():
            params = cls.parameters
            properties = list(params.get("properties", {}))
            required = list(params.get("required", []))
            first_n = properties[: len(required)]
            assert set(required) == set(first_n), (
                f"tool {name!r}: required {required} is not the first-"
                f"{len(required)} declared properties {first_n}; "
                "declaration-order positional binding would mis-bind"
            )


def test_sentinel_constant_matches_kernel() -> None:
    # The constant is duplicated (not imported) across the layer boundary;
    # this guards the two literals from drifting apart.
    from the_one.llm._toolcall_recovery import (
        POSITIONAL_ARGS_KEY as KERNEL_KEY,
    )

    assert POSITIONAL_ARGS_KEY == KERNEL_KEY
