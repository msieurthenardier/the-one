"""Tests for the context-budget governor (M16 F08 L01 / DD1).

Two layers:

1. ``govern_tool_content`` — the PURE helper, unit-tested in isolation (no
   agent/LLM construction): large-valid → capped, small → unchanged,
   scales-with-window, floor/ceiling clamp, head vs tail direction, the
   ``max_context_tokens`` floor (LOW-2), and the marker-outside-budget invariant.

2. Cross-tool boundary tests (the F07 verification miss) — drive real tools
   (web / filesystem) plus a tail-direction tool through ``Agent._execute_tool``
   and assert a large *valid* result reaching the model is bounded, a small one
   passes unchanged, an error-string result is bounded too, and the shell tail
   (``[exit code: N]`` + stderr tail) survives tail-preserving truncation.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests._old_prompts import OLD_PLATFORM_TOOLS as PLATFORM_TOOLS
from tests.conftest import FakeLLM
from the_one.agent._governor import (
    _DEFAULT_CEILING_BYTES,
    _DEFAULT_FLOOR_BYTES,
    _MAX_CONTEXT_TOKENS_FLOOR,
    govern_tool_content,
    governor_defaults,
)
from the_one.agent.core import Agent
from the_one.llm.base import ToolCall
from the_one.tools._web_config import WebConfig
from the_one.tools.base import Tool, ToolRegistry
from the_one.tools.execution import ExecutionConfig, _truncate_output
from the_one.tools.web import HttpRequestTool

# Common kwargs for the pure helper at the production defaults.
_DEFAULTS = dict(
    fraction=1 / 8,
    floor=_DEFAULT_FLOOR_BYTES,
    ceiling=_DEFAULT_CEILING_BYTES,
    bytes_per_token=4.0,
)


# ---------------------------------------------------------------------------
# 1. Pure helper
# ---------------------------------------------------------------------------


class TestGovernToolContentPure:
    def test_large_valid_is_capped(self) -> None:
        # 128k tokens * 1/8 * 4 bytes = 64 KB budget. A 200 KB payload is cut.
        content = "A" * 200_000
        out = govern_tool_content(content, 128_000, direction="head", **_DEFAULTS)
        assert len(out.encode("utf-8")) < 200_000
        assert "governor truncated" in out

    def test_small_content_unchanged(self) -> None:
        content = "hello world"
        out = govern_tool_content(content, 128_000, direction="head", **_DEFAULTS)
        assert out == content
        assert "governor truncated" not in out

    def test_cap_scales_with_window(self) -> None:
        # A 1M-token window yields a larger budget than a 128k window, so the
        # same large payload survives more bytes (until the ceiling clamps).
        content = "A" * 400_000
        small = govern_tool_content(content, 128_000, direction="head", **_DEFAULTS)
        # Use a higher ceiling so the larger window actually scales up.
        kw = {**_DEFAULTS, "ceiling": 10_000_000}
        large = govern_tool_content(content, 1_000_000, direction="head", **kw)
        small_kept = govern_tool_content(content, 128_000, direction="head", **kw)
        assert len(large.encode("utf-8")) > len(small_kept.encode("utf-8"))
        # And both are bounded below the raw input.
        assert len(small.encode("utf-8")) < len(content.encode("utf-8"))

    def test_floor_applies_for_tiny_window_via_fraction(self) -> None:
        # A tiny fraction would compute a sub-floor budget; the floor wins.
        content = "A" * 100_000
        kw = {**_DEFAULTS, "fraction": 1 / 1_000_000}  # ~0.5 bytes pre-clamp
        out = govern_tool_content(content, 128_000, direction="head", **kw)
        # The kept head is exactly the floor (marker excluded).
        head = out.split("\n\n[... governor truncated", 1)[0]
        assert len(head.encode("utf-8")) == _DEFAULT_FLOOR_BYTES

    def test_ceiling_clamps_huge_window(self) -> None:
        # A 10M-token window would compute a 5 MB budget; the ceiling caps it.
        content = "A" * 1_000_000
        out = govern_tool_content(content, 10_000_000, direction="head", **_DEFAULTS)
        head = out.split("\n\n[... governor truncated", 1)[0]
        assert len(head.encode("utf-8")) == _DEFAULT_CEILING_BYTES

    def test_max_context_tokens_floored(self) -> None:
        # 0 / None / absurdly-small all floor to 128k (LOW-2): identical budget.
        content = "A" * 200_000
        a = govern_tool_content(content, 0, direction="head", **_DEFAULTS)
        b = govern_tool_content(content, None, direction="head", **_DEFAULTS)
        c = govern_tool_content(content, 5, direction="head", **_DEFAULTS)
        d = govern_tool_content(content, _MAX_CONTEXT_TOKENS_FLOOR, direction="head", **_DEFAULTS)
        assert a == b == c == d

    def test_head_preserves_start(self) -> None:
        content = "HEAD" + "x" * 200_000 + "TAIL"
        out = govern_tool_content(content, 128_000, direction="head", **_DEFAULTS)
        assert out.startswith("HEAD")
        assert "TAIL" not in out
        assert out.rstrip().endswith("...]")  # marker at the end

    def test_tail_preserves_end(self) -> None:
        content = "HEAD" + "x" * 200_000 + "TAIL"
        out = govern_tool_content(content, 128_000, direction="tail", **_DEFAULTS)
        assert out.endswith("TAIL")
        assert "HEAD" not in out
        assert out.startswith("[... governor truncated")  # marker at the start

    def test_marker_sits_outside_budget(self) -> None:
        # The kept slice is EXACTLY the budget; the returned length exceeds the
        # budget by the marker (marker is NOT counted against the budget).
        content = "A" * 200_000
        budget = int(1 / 8 * 128_000 * 4.0)  # 64 KB
        out = govern_tool_content(content, 128_000, direction="head", **_DEFAULTS)
        head = out.split("\n\n[... governor truncated", 1)[0]
        assert len(head.encode("utf-8")) == budget
        assert len(out.encode("utf-8")) > budget  # marker pushed it over

    def test_multibyte_boundary_no_exception(self) -> None:
        # A budget that slices mid-codepoint must decode with replacement, not
        # raise. Build content of multibyte chars sized to force a mid-char cut.
        content = "€" * 100_000  # 3 bytes each = 300 KB
        out = govern_tool_content(content, 128_000, direction="head", **_DEFAULTS)
        assert isinstance(out, str)  # decoded, did not raise
        assert "governor truncated" in out


class TestGovernorDefaults:
    def test_defaults(self) -> None:
        fraction, floor, ceiling = governor_defaults()
        assert fraction == pytest.approx(1 / 8)
        assert floor == _DEFAULT_FLOOR_BYTES == 8_192
        assert ceiling == _DEFAULT_CEILING_BYTES == 262_144

    def test_env_override(self, monkeypatch) -> None:
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_FRACTION", "0.25")
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_FLOOR", "4096")
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_CEILING", "524288")
        fraction, floor, ceiling = governor_defaults()
        assert fraction == pytest.approx(0.25)
        assert floor == 4096
        assert ceiling == 524288

    def test_floor_clamped_above_marker(self, monkeypatch) -> None:
        # A pathologically tiny floor is clamped so the marker can't exceed it.
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_FLOOR", "1")
        _, floor, _ = governor_defaults()
        assert floor >= 256


# ---------------------------------------------------------------------------
# 2. Cross-tool boundary tests (Agent._execute_tool)
# ---------------------------------------------------------------------------


class _BigResultTool(Tool):
    """Tool returning a caller-chosen string with a chosen truncation direction.

    Stands in for any tool at the dispatch boundary so the cross-tool
    governor coverage doesn't need a sandbox (shell/exec) to prove the
    direction-aware bound. The web/filesystem cases below exercise REAL tools.
    """

    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(self, name: str, payload: str, direction: str = "head") -> None:
        self.name = name
        self.description = "big result"
        self._payload = payload
        self.truncation_direction = direction  # type: ignore[assignment]
        self._cross_configs = {}
        self._agent_name = None
        self._config = self.Config()

    async def execute(self, **kwargs: Any) -> str:
        return self._payload


def _agent_with(registry: ToolRegistry) -> Agent:
    return Agent(llm=FakeLLM(responses=[]), tools=registry, system_prompt=PLATFORM_TOOLS)


def _call(name: str) -> ToolCall:
    return ToolCall(id="t1", name=name, arguments={})


class TestGovernorAtDispatchBoundary:
    async def test_large_valid_result_is_bounded(self) -> None:
        reg = ToolRegistry()
        reg.register(_BigResultTool("big", "A" * 500_000))
        agent = _agent_with(reg)
        result = await agent._execute_tool(_call("big"))
        # Bounded to the 256 KB ceiling (+ marker), well below the 500 KB raw.
        assert len(result.content.encode("utf-8")) < 300_000
        assert "governor truncated" in result.content
        assert result.is_error is False

    async def test_small_result_passes_unchanged(self) -> None:
        reg = ToolRegistry()
        reg.register(_BigResultTool("small", "tiny output"))
        agent = _agent_with(reg)
        result = await agent._execute_tool(_call("small"))
        assert result.content == "tiny output"
        assert "governor truncated" not in result.content

    async def test_cap_scales_with_model_window(self, monkeypatch) -> None:
        # Raise the ceiling so the larger window can actually scale the budget.
        monkeypatch.setenv("THE_ONE_TOOL_RESULT_BUDGET_CEILING", "10000000")
        reg = ToolRegistry()
        reg.register(_BigResultTool("big", "A" * 2_000_000))
        agent = _agent_with(reg)

        agent.llm.max_context_tokens = 128_000
        small = await agent._execute_tool(_call("big"))
        agent.llm.max_context_tokens = 1_000_000
        large = await agent._execute_tool(_call("big"))
        assert len(large.content.encode("utf-8")) > len(small.content.encode("utf-8"))

    async def test_error_string_result_is_bounded(self) -> None:
        # A tool that raises a huge exception payload — the generic-except path
        # governs the error string too.
        class _Boom(_BigResultTool):
            async def execute(self, **kwargs: Any) -> str:
                raise RuntimeError("E" * 500_000)

        reg = ToolRegistry()
        reg.register(_Boom("boom", ""))
        agent = _agent_with(reg)
        result = await agent._execute_tool(_call("boom"))
        assert result.is_error is True
        assert len(result.content.encode("utf-8")) < 300_000
        assert "governor truncated" in result.content

    async def test_shell_tail_is_preserved(self) -> None:
        # Build a REAL shell-shaped result via _truncate_output (stdout + stderr
        # + [exit code: N] suffix) large enough to exceed the budget, then run it
        # through the tail-direction boundary. The diagnostic tail must survive.
        cfg = ExecutionConfig(output_cap_bytes=104_857_600)  # don't pre-trim here
        stdout = b"X" * 1_000_000
        stderr = b"FATAL: build failed at the end"
        text, _ = _truncate_output(stdout, stderr, 2, cfg)
        assert text.rstrip().endswith("[exit code: 2]")  # precondition

        reg = ToolRegistry()
        reg.register(_BigResultTool("shell", text, direction="tail"))
        agent = _agent_with(reg)
        result = await agent._execute_tool(_call("shell"))

        assert len(result.content.encode("utf-8")) < 300_000  # bounded
        assert "governor truncated" in result.content
        # The exit-code suffix + stderr tail (the diagnostic part) survived.
        assert "[exit code: 2]" in result.content
        assert "FATAL: build failed" in result.content

    async def test_web_large_valid_result_is_bounded(self, monkeypatch) -> None:
        # REAL web tool: a 400 KB text body (under the 1 MB transport cap) reaches
        # the dispatch boundary uncapped by the tool, then the governor bounds it.
        big = "W" * 400_000
        monkeypatch.setattr(
            HttpRequestTool,
            "_build_transport",
            lambda self, cfg: httpx.MockTransport(
                lambda req: httpx.Response(200, text=big, headers={"content-type": "text/plain"})
            ),
        )
        reg = ToolRegistry()
        reg.register(HttpRequestTool(WebConfig()))
        agent = _agent_with(reg)
        call = ToolCall(
            id="t1", name="http_request", arguments={"method": "GET", "url": "https://x.test/"}
        )
        result = await agent._execute_tool(call)
        assert len(result.content.encode("utf-8")) < 300_000  # governor-bounded
        assert "governor truncated" in result.content
        assert result.content.startswith("[200]")  # head preserved (web = head)

    async def test_filesystem_large_valid_result_is_bounded(self, tmp_path, monkeypatch) -> None:
        # REAL filesystem tool: a large readable file under the allowlist.
        from the_one.tools.filesystem import FilesystemConfig, ReadFileTool

        big_file = tmp_path / "big.txt"
        big_file.write_text("F" * 500_000)
        cfg = FilesystemConfig(
            path_allowlist=[str(tmp_path)],
            read_size_cap_bytes=10_000_000,  # don't trip the file-size safety guard
        )
        reg = ToolRegistry()
        reg.register(ReadFileTool(cfg))
        agent = _agent_with(reg)
        call = ToolCall(id="t1", name="read_file", arguments={"path": str(big_file)})
        result = await agent._execute_tool(call)
        assert result.is_error is False
        assert len(result.content.encode("utf-8")) < 300_000  # governor-bounded
        assert "governor truncated" in result.content

    async def test_auth_required_sentinel_not_governed(self) -> None:
        # LOW-3: the MCP auth-required sentinel must pass through untouched.
        from the_one.mcp.errors import MCPAuthRequired

        class _AuthTool(_BigResultTool):
            async def execute(self, **kwargs: Any) -> str:
                raise MCPAuthRequired("s", source_name="n")

        reg = ToolRegistry()
        reg.register(_AuthTool("auth", ""))
        agent = _agent_with(reg)
        result = await agent._execute_tool(_call("auth"))
        assert result.content == "<auth required>"
        assert result.metadata and result.metadata.get("is_auth_required") is True
