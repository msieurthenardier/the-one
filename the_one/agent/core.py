from __future__ import annotations

import json
import re
import uuid
from typing import AsyncIterator

from the_one.llm.base import LLMProvider, Message, ToolCall, ToolResult
from the_one.tools.base import ToolRegistry

# Direct-action patterns: map user intent to tool calls without LLM interpretation.
# Needed because small models often reach for shell instead of the right tool.
_DIRECT_ACTIONS: list[tuple[re.Pattern[str], str, dict]] = [
    (re.compile(r"^(please\s+)?(restart|reboot|reload)\s+(yourself|the agent|the container|the app)", re.I), "restart", {}),
    (re.compile(r"^(please\s+)?(roll\s*back|undo\s+deploy)", re.I), "rollback", {}),
]

# The agent can call this to keep its turn. It's a signal, not a real tool.
_CONTINUE_SCHEMA = {
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

SYSTEM_PROMPT = """\
You are "the-one", a personal AI agent. You have access to tools that let you \
interact with the computer, filesystem, web, and more. Use them to accomplish \
whatever the user asks.

You can read and modify your own source code under /workspace, run tests, \
deploy new versions of yourself, and roll back if things break.

Architecture:
- /app = your running code (stable, copied at build time)
- /workspace = mounted source repo (you edit here, changes take effect after deploy)

Self-management tools:
- restart: Restart your container immediately (no rebuild, same code). Use when \
asked to "restart yourself", "reboot", etc.
- run_tests: Run pytest against /workspace code before deploying.
- git: Git operations on /workspace (status, diff, add, commit, log, etc.).
- self_deploy: Full deploy — rebuild image from /workspace code and restart. \
Use after editing your own source code.
- rollback: Restore the previous Docker image and restart. Use if a deploy broke things.

Self-modification workflow:
1. Read/edit files under /workspace using filesystem tools
2. Run tests with the run_tests tool to verify changes
3. Commit changes with the git tool
4. Deploy with self_deploy (rebuilds image, restarts container)
5. If something breaks, use rollback to restore the previous version

Workflow methodology:
You follow the Mission Control methodology (docs at /mission-control/docs/). \
Read these docs to understand the framework. The key structure is:
- Mission: an outcome someone wants (human-written, days-weeks)
- Flight: a technical plan to achieve part of a mission (hours-days)
- Leg: a single discrete task you can execute (minutes-hours)

When given complex work, break it into legs. Each leg should have:
- A clear objective (one sentence)
- Acceptance criteria (binary, observable)
- Files likely affected

Execute one leg at a time. After each leg, verify acceptance criteria before \
moving on. Record what actually happened — deviations matter.

Your workspace artifacts live in /workspace/.flightops/

Guidelines:
- Use tools when actions are needed — don't just describe what you would do.
- Be concise and direct in your responses.
- If a task requires multiple steps, break them into legs and execute sequentially.
- If something fails, try alternative approaches before giving up.
- Always run tests before deploying changes to yourself.
- Be cautious with self-modifications — bad changes can break you.
- When asked to restart, reboot, or reset yourself, use the restart tool. \
Do NOT simulate a restart with shell commands.
- If you have more work to do, call the continue tool to keep your turn. \
If you're done, just respond without calling any tools.
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

    def _tool_schemas(self) -> list[dict]:
        """All tool schemas including the continue signal."""
        schemas = self.tools.all_schemas() or []
        return schemas + [_CONTINUE_SCHEMA]

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
        """Extract tool calls from JSON embedded in assistant text.

        Looks for patterns like:
          {"name": "tool_name", "arguments": {...}}
          {"name": "tool_name", "arguments": "string_arg"}
        Only extracts calls for tools that actually exist in the registry.
        """
        valid_names = set(self.tools.tool_names) | {"continue"}
        calls: list[ToolCall] = []
        # Match JSON objects that have "name" and "arguments" keys
        for match in re.finditer(r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:[^}]+\}', text):
            try:
                obj = json.loads(match.group())
            except json.JSONDecodeError:
                continue
            name = obj.get("name", "")
            args = obj.get("arguments", {})
            if name not in valid_names:
                continue
            if isinstance(args, str):
                args = {"args": args}
            if not isinstance(args, dict):
                continue
            calls.append(ToolCall(
                id=f"extracted-{uuid.uuid4().hex[:8]}",
                name=name,
                arguments=args,
            ))
        return calls

    @staticmethod
    def _match_direct_action(user_input: str) -> tuple[str, dict] | None:
        """Match user input against direct-action patterns."""
        text = user_input.strip()
        for pattern, tool_name, kwargs in _DIRECT_ACTIONS:
            if pattern.search(text):
                return tool_name, kwargs
        return None

    def reset(self) -> None:
        self.messages = [Message.system(self.system_prompt)]
