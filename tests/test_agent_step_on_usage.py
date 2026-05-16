"""F7 L04: Agent.step on_usage callback contract.

Covers:
- on_usage fires once per interim StreamChunk that carries usage
- on_usage does NOT fire for the final StreamChunk's usage (the caller's
  final-usage broadcast path handles end-of-step accumulation; avoiding
  double-emission was a cycle-1 [high] correction)
- on_usage is optional — providers that never emit interim usage and
  callers that omit on_usage both work unchanged
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from the_one.agent.core import Agent
from the_one.llm.base import LLMProvider, Message, StreamChunk, TokenUsage
from the_one.tools.base import ToolRegistry


class _InterimUsageProvider(LLMProvider):
    """Fake provider emitting 3 interim usage chunks then a final chunk.

    Used to assert the on_usage callback contract: interim-only emission,
    one call per non-final StreamChunk whose ``usage`` is non-None.
    """

    name = "interim-usage-fake"

    def __init__(self, interim_usages: list[TokenUsage]) -> None:
        super().__init__()
        self._interim_usages = list(interim_usages)

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> Message:
        # Not exercised by the streaming-path test, but required by the
        # abstract base class.
        return Message.assistant(content="unused")

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 16384,
    ) -> AsyncIterator[StreamChunk]:
        # Interleave content deltas with usage-only interim chunks, then
        # close with a final chunk that ALSO carries usage. The on_usage
        # callback must fire for each interim usage chunk and NOT for the
        # final one (interim-only contract).
        for i, usage in enumerate(self._interim_usages):
            yield StreamChunk(content=f"chunk{i} ", is_final=False)
            yield StreamChunk(content="", is_final=False, usage=usage)
        final_msg = Message.assistant(
            content="chunk0 chunk1 chunk2 ",
            usage=TokenUsage(input_tokens=10, output_tokens=99),
        )
        yield StreamChunk(
            content="",
            is_final=True,
            usage=TokenUsage(input_tokens=10, output_tokens=99),
            message=final_msg,
        )


class TestOnUsageCallback:
    async def test_on_usage_fires_once_per_interim_chunk(self) -> None:
        provider = _InterimUsageProvider(
            interim_usages=[
                TokenUsage(input_tokens=0, output_tokens=50),
                TokenUsage(input_tokens=0, output_tokens=100),
                TokenUsage(input_tokens=0, output_tokens=150),
            ]
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")
        seen: list[TokenUsage] = []

        async def _on_usage(usage: TokenUsage) -> None:
            seen.append(usage)

        async for _ in agent.step("hi", on_usage=_on_usage):
            pass

        assert len(seen) == 3, f"expected 3 interim emissions, got {len(seen)}"
        # Output tokens are monotonically increasing (cumulative semantics).
        assert [u.output_tokens for u in seen] == [50, 100, 150]

    async def test_on_usage_skips_final_chunk_usage(self) -> None:
        # The final chunk's usage (output_tokens=99) MUST NOT fire on_usage
        # — the caller's existing final-usage path handles it. Verify by
        # asserting none of the seen values matches the final synthesized
        # usage payload.
        provider = _InterimUsageProvider(
            interim_usages=[TokenUsage(input_tokens=0, output_tokens=42)]
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")
        seen: list[TokenUsage] = []

        async def _on_usage(usage: TokenUsage) -> None:
            seen.append(usage)

        async for _ in agent.step("hi", on_usage=_on_usage):
            pass

        # Exactly one fire (the interim), NOT two (interim + final).
        assert len(seen) == 1
        assert seen[0].output_tokens == 42

    async def test_on_usage_none_is_back_compat(self) -> None:
        # Caller omits on_usage — step must complete without error and
        # yield the synthesised final Message normally.
        provider = _InterimUsageProvider(
            interim_usages=[TokenUsage(input_tokens=0, output_tokens=10)]
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")
        messages = []
        async for m in agent.step("hi"):
            messages.append(m)
        assert len(messages) == 1
        assert messages[0].content == "chunk0 chunk1 chunk2 "

    async def test_on_usage_never_fires_for_no_interim_provider(self) -> None:
        # Provider that emits zero interim usage chunks → on_usage never
        # fires; step completes normally.
        from the_one.llm.mock import MockProvider

        provider = MockProvider(
            model="mock-default",
            config={"stream_chunks": ["a", "b"], "delay_ms": 0},
        )
        agent = Agent(llm=provider, tools=ToolRegistry(), system_prompt="sys")
        seen: list[TokenUsage] = []

        async def _on_usage(usage: TokenUsage) -> None:
            seen.append(usage)

        async for _ in agent.step("hi", on_usage=_on_usage):
            pass

        assert seen == []
