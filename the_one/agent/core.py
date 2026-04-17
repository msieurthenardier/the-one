from __future__ import annotations

from typing import AsyncIterator

from the_one.llm.base import LLMProvider, Message, ToolCall, ToolResult
from the_one.tools.base import ToolRegistry

SYSTEM_PROMPT = """\
You are "the-one", a personal AI agent. You have access to tools that let you \
interact with the computer, filesystem, web, and more. Use them to accomplish \
whatever the user asks.

Guidelines:
- Think step by step about complex tasks.
- Use tools when actions are needed — don't just describe what you would do.
- Be concise and direct in your responses.
- If a task requires multiple steps, execute them sequentially.
- If something fails, try alternative approaches before giving up.
"""


class Agent:
    """The core agent loop: take user input, call LLM, execute tools, repeat."""

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str = SYSTEM_PROMPT,
        max_iterations: int = 20,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.messages: list[Message] = [Message.system(system_prompt)]

    async def step(self, user_input: str) -> AsyncIterator[Message]:
        """Process a user message through the agent loop.

        Yields each assistant/tool message as it's produced.
        """
        self.messages.append(Message.user(user_input))

        for _ in range(self.max_iterations):
            response = await self.llm.complete(
                messages=self.messages,
                tools=self.tools.all_schemas() or None,
            )
            self.messages.append(response)
            yield response

            if not response.tool_calls:
                break

            # Execute all tool calls
            for tc in response.tool_calls:
                result = await self._execute_tool(tc)
                tool_msg = Message.tool(result)
                self.messages.append(tool_msg)
                yield tool_msg

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
