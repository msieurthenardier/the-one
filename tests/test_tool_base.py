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
