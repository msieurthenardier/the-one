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

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from the_one.tools.base import Tool
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
