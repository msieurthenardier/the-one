from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from the_one.llm.base import LLMProvider, Message, ToolCall, ToolResult
from the_one.tools.base import ToolRegistry

# The agent can call this to keep its turn. It's a signal, not a real tool.
CONTINUE_SCHEMA = {
    "name": "continue",
    "description": (
        "Call this when you're not done yet — you have more steps to take "
        "but need another turn to think or act. If you don't call this or "
        "any other tool, your turn ends and the user sees your response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Brief note to yourself about what you're doing next.",
            },
        },
        "required": [],
    },
}


class Agent:
    """The core agent loop: take user input, call LLM, execute tools, repeat."""

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str,
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
        synthesised final ``Message`` flows up via ``yield``.
        """
        self.messages.append(Message.user(user_input))

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

    def reset(self) -> None:
        self.messages = [Message.system(self.system_prompt)]
