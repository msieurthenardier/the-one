from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from the_one.agent.behaviors import CONTINUE_SCHEMA, match_direct_action
from the_one.agent.config import DEFAULT_SYSTEM_PROMPT
from the_one.llm.base import LLMProvider, Message, ToolCall, ToolResult
from the_one.tools.base import ToolRegistry


class Agent:
    """The core agent loop: take user input, call LLM, execute tools, repeat."""

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_iterations: int = 20,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.messages: list[Message] = [Message.system(system_prompt)]

    def _tool_schemas(self) -> list[dict]:
        """All tool schemas including the continue signal."""
        schemas = self.tools.all_schemas() or []
        return schemas + [CONTINUE_SCHEMA]

    async def step(
        self,
        user_input: str,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AsyncIterator[Message]:
        """Process a user message through the agent loop.

        Yields each assistant/tool message as it's produced.

        ``on_chunk``: optional async callback invoked once per content chunk
        during streaming. Callers that omit ``on_chunk`` get the original
        Message-yielding semantics; chunks fan out internally but only the
        synthesised final ``Message`` flows up via ``yield``. Direct-action
        responses bypass the LLM entirely so ``on_chunk`` is never invoked
        on that path.
        """
        self.messages.append(Message.user(user_input))

        # Check for direct-action patterns before calling the LLM
        direct = self._match_direct_action(user_input)
        if direct:
            tool_name, tool_kwargs = direct
            try:
                tool = self.tools.get(tool_name)
                output = await tool.execute(**tool_kwargs)
            except Exception as e:
                output = f"[error] {e}"
            msg = Message.assistant(content=output)
            self.messages.append(msg)
            yield msg
            return

        for _ in range(self.max_iterations):
            accumulated_text = ""
            final_chunk = None
            async for chunk in self.llm.stream(
                messages=self.messages,
                tools=self._tool_schemas() or None,
            ):
                if chunk.content:
                    accumulated_text += chunk.content
                    if on_chunk:
                        await on_chunk(chunk.content)
                if chunk.is_final:
                    final_chunk = chunk
                    break

            # Synthesize the response Message — prefer the provider's
            # synthesized Message if available; otherwise rebuild it from
            # accumulated state.
            if final_chunk is not None and final_chunk.message is not None:
                response = final_chunk.message
            else:
                response = Message.assistant(
                    content=accumulated_text,
                    tool_calls=(final_chunk.tool_calls if final_chunk else []),
                    usage=(final_chunk.usage if final_chunk else None),
                )
            self.messages.append(response)
            yield response

            if not response.tool_calls:
                break

            # Process tool calls — continue is just a signal, everything else executes
            has_real_tool = False
            for tc in response.tool_calls:
                if tc.name == "continue":
                    # Acknowledge the continue — feed it back so the model sees it worked
                    reason = tc.arguments.get("reason", "")
                    tool_msg = Message.tool(ToolResult(
                        tool_call_id=tc.id,
                        content=reason or "continuing...",
                    ))
                    self.messages.append(tool_msg)
                    has_real_tool = True  # keep the loop going
                else:
                    result = await self._execute_tool(tc)
                    tool_msg = Message.tool(result)
                    self.messages.append(tool_msg)
                    yield tool_msg
                    has_real_tool = True

            if not has_real_tool:
                break

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        try:
            tool = self.tools.get(tool_call.name)
            output = await tool.execute(**tool_call.arguments)
            return ToolResult(tool_call_id=tool_call.id, content=output)
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call.id,
                content=f"[error] Tool execution failed: {e}",
                is_error=True,
            )

    @staticmethod
    def _match_direct_action(user_input: str) -> tuple[str, dict] | None:
        """Delegate to standalone match_direct_action function."""
        return match_direct_action(user_input)

    def reset(self) -> None:
        self.messages = [Message.system(self.system_prompt)]
