from __future__ import annotations

from typing import AsyncIterator

from the_one.agent.behaviors import CONTINUE_SCHEMA, extract_tool_calls, match_direct_action
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

    async def step(self, user_input: str) -> AsyncIterator[Message]:
        """Process a user message through the agent loop.

        Yields each assistant/tool message as it's produced.
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
            response = await self.llm.complete(
                messages=self.messages,
                tools=self._tool_schemas() or None,
            )
            self.messages.append(response)
            yield response

            # If the LLM didn't produce formal tool calls, try to extract
            # JSON tool calls embedded in the text (common with smaller models).
            if not response.tool_calls and response.content:
                extracted = self._extract_tool_calls(response.content)
                if extracted:
                    response.tool_calls = extracted

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

    def _extract_tool_calls(self, text: str) -> list[ToolCall]:
        """Delegate to standalone extract_tool_calls function."""
        return extract_tool_calls(text, set(self.tools.tool_names) | {"continue"})

    @staticmethod
    def _match_direct_action(user_input: str) -> tuple[str, dict] | None:
        """Delegate to standalone match_direct_action function."""
        return match_direct_action(user_input)

    def reset(self) -> None:
        self.messages = [Message.system(self.system_prompt)]
