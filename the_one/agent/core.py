from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable

from the_one.agent._context import current_tool_call_id
from the_one.llm.base import LLMProvider, Message, ToolCall, ToolResult
from the_one.mcp.errors import MCPAuthRequired
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

# F10 L1: strict baseline (§2). search_tools is the ONLY non-`continue`
# schema visible to the LLM at session start. Additional schemas are added
# to the model-visible set as a side effect of calling search_tools.
# F10 follow-up: search_tools and search_mcps were merged into a single
# tool that covers both the built-in catalog and any attached MCP servers.
SEARCH_TOOLS_SCHEMA = {
    "name": "search_tools",
    "description": (
        "Search every tool available to you — built-in tools (shell, file "
        "operations, web fetch, etc.) AND tools from any MCP servers "
        "attached to this agent — for ones matching a query. Matched tools "
        "are automatically added to your available toolset for the rest of "
        "this conversation. Call with an empty query to list every tool "
        "available to you."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Substring to search for in tool names and descriptions. "
                    "Empty string returns all."
                ),
            },
        },
        "required": [],
    },
}


class Agent:
    """The core agent loop: take user input, call LLM, execute tools, repeat.

    Pause state (``_deferred_tool_calls``, ``_remaining_iterations``) is
    in-memory only — server restart loses the pause and the operator
    must re-trigger the original tool call. Session replay via
    ``messages_to_ui_events`` does NOT propagate ``metadata``;
    historical paused conversations show the auth_required tool_msg as
    informational text without the Login-required affordance.
    """

    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str,
        max_iterations: int = 20,
        *,
        loaded_schemas: list[dict] | None = None,
        loaded_tool_names: set[str] | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.messages: list[Message] = [Message.system(system_prompt)]
        # F5 L3: pause/resume state (in-memory only; not persisted —
        # see class docstring). Set by ``step``; consumed by
        # ``resume_after_auth``.
        self._deferred_tool_calls: list[ToolCall] | None = None
        self._remaining_iterations: int = 0
        # F10 L1: visibility filter. SHARED CONTAINERS with the factory-
        # constructed search-stub tools — mutations from those tools land
        # in these containers; _compute_visible_schemas reads them.
        # Defaults to fresh empty containers if omitted (backward-compat
        # for non-factory Agent construction sites, e.g. tests).
        self._loaded_schemas: list[dict] = loaded_schemas if loaded_schemas is not None else []
        self._loaded_tool_names: set[str] = loaded_tool_names if loaded_tool_names is not None else set()

    def _compute_visible_schemas(self) -> list[dict]:
        """F10 L1: per-iteration model-visible schemas.

        Returns the baseline (search_tools + continue) plus any schemas the
        search tool has loaded into the visibility set as a side effect of
        being called. The Agent's ToolRegistry holds the FULL candidate
        set; this method computes the filtered view the LLM sees on each
        iteration's tools= array.
        """
        return [SEARCH_TOOLS_SCHEMA, CONTINUE_SCHEMA] + self._loaded_schemas

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
        # F5 L3: clear stale pause state at the start of a new step and
        # re-prime the iteration budget. ``_run_iterations`` decrements
        # ``_remaining_iterations`` at the top of each iteration body.
        self._deferred_tool_calls = None
        self._remaining_iterations = self.max_iterations
        async for msg in self._run_iterations(on_chunk):
            yield msg

    async def _run_iterations(
        self,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> AsyncIterator[Message]:
        """The iteration loop body — extracted for ``resume_after_auth`` re-use.

        Reads ``self._remaining_iterations`` and decrements at the top of
        each iteration body. On pause (any tool returns
        ``metadata.is_auth_required``), ``_dispatch_tool_calls`` sets
        ``self._deferred_tool_calls`` and this helper returns; the
        remaining iteration budget is preserved on the instance for a
        subsequent ``resume_after_auth`` call.
        """
        # Resolve supports_tools ONCE per _run_iterations entry (network call
        # in some provider implementations). The schemas computation moves
        # inside the while loop so search-driven additions to _loaded_schemas
        # show up on the next iteration's tools= array.
        # If the model can't accept tools (e.g. Ollama Gemma), drop
        # everything — including the virtual ``continue`` signal AND any real
        # tools — and run as a single-shot chat. Studio surfaces this via the
        # red "no tools" capability chip on the model selector, so the operator
        # already had the chance to know; silently degrading is preferable to
        # refusing the message at send time.
        supports_tools = await self.llm.supports_tools()

        while self._remaining_iterations > 0:
            self._remaining_iterations -= 1  # F5 L3: consume one iteration up-front

            # F10 L1: per-iteration visibility filter recompute so that
            # search-driven mutations to _loaded_schemas from iteration N
            # appear in iteration N+1's tools= array.
            if supports_tools:
                tool_schemas = self._compute_visible_schemas()
            else:
                tool_schemas = []

            accumulated_text = ""
            final_chunk = None
            async for chunk in self.llm.stream(
                messages=self.messages,
                tools=tool_schemas or None,
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
                return  # text-only response — done

            # F5 L3: dispatch tool calls through the helper; if any tool
            # returns ``metadata.is_auth_required``, the helper captures
            # current + remaining tool calls into ``_deferred_tool_calls``
            # and returns; we then exit so the WebSocket layer can
            # broadcast the auth_required event without a follow-up
            # ``done``.
            async for tool_msg in self._dispatch_tool_calls(response.tool_calls):
                yield tool_msg

            if self._deferred_tool_calls is not None:
                return  # paused — exit; remaining iterations preserved

    async def _dispatch_tool_calls(
        self, tcs: list[ToolCall]
    ) -> AsyncIterator[Message]:
        """Dispatch a list of tool calls in order.

        ``continue`` virtual signal: appends but does not yield (matches
        the pre-L3 semantic — the synthesized ToolResult has
        ``metadata=None`` by construction so the auth_required check
        short-circuits cleanly).

        Real tools: calls ``_execute_tool``, appends + yields the
        tool_msg. If any tool returns ``metadata.is_auth_required``,
        captures current + remaining tool calls into
        ``self._deferred_tool_calls`` and exits early. Caller is
        responsible for checking ``self._deferred_tool_calls`` after
        the iterator drains.
        """
        for i, tc in enumerate(tcs):
            if tc.name == "continue":
                # Continue virtual signal — preserved verbatim from the
                # pre-L3 ``Agent.step`` semantic. Acknowledge the
                # continue by feeding the reason back so the model sees
                # it worked. NOT yielded — the caller doesn't surface
                # this to the chat UI. ``metadata=None`` by construction
                # short-circuits the auth_required check (F5 §4 carve-out).
                reason = tc.arguments.get("reason", "")
                tool_msg = Message.tool(
                    ToolResult(
                        tool_call_id=tc.id,
                        content=reason or "continuing...",
                    )
                )
                self.messages.append(tool_msg)
                continue

            result = await self._execute_tool(tc)
            tool_msg = Message.tool(result)
            self.messages.append(tool_msg)
            yield tool_msg

            # F5 L3: pause/resume check — must be AFTER append+yield so
            # chat history reflects the auth_required surface and the
            # WebSocket layer can broadcast the event. Capture current +
            # remaining tool calls so ``resume_after_auth`` can re-dispatch
            # them in order (slice-from-current-index pattern works at
            # index 0 too — covered by A8b).
            if result.metadata and result.metadata.get("is_auth_required"):
                self._deferred_tool_calls = list(tcs[i:])
                return

    async def resume_after_auth(self) -> AsyncIterator[Message]:
        """Re-dispatch deferred tool calls after ``auth_resolved``.

        Reads ``self._deferred_tool_calls`` (set by
        ``_dispatch_tool_calls`` on pause). No-op when None — protects
        against accidental re-entry.

        On resume:
          1. Clears the deferred field BEFORE re-dispatch so a re-pause
             can set it again (A8 re-pause path).
          2. Re-dispatches via ``_dispatch_tool_calls``.
          3. If re-paused (deferred set again), exits — caller will
             receive another ``auth_resolved`` later.
          4. Otherwise continues the iteration loop with the remaining
             iteration budget on ``self._remaining_iterations``.
        """
        if self._deferred_tool_calls is None:
            return  # A7 no-op

        deferred = self._deferred_tool_calls
        self._deferred_tool_calls = None  # consumed before re-dispatch

        async for tool_msg in self._dispatch_tool_calls(deferred):
            yield tool_msg

        if self._deferred_tool_calls is not None:
            return  # re-paused (A8)

        # Continue normally with remaining iteration budget. The while-
        # loop guard in ``_run_iterations`` handles ``=0`` correctly so
        # we don't blow past ``max_iterations`` even if the original
        # step had already exhausted the budget.
        async for msg in self._run_iterations():
            yield msg

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        # F6 L3: bind tool_call_id into the per-task ContextVar so the
        # MCP pool's _entry_worker (and the OAuth handlers it wires)
        # can attach the originating tool_call_id to any auth_required
        # broadcast. Reset in finally — the inner try/except blocks
        # handle MCPAuthRequired translation (F5 L4) and generic
        # exception fall-through, both of which return through the
        # outer finally.
        token = current_tool_call_id.set(tool_call.id)
        try:
            try:
                tool = self.tools.get(tool_call.name)
                output = await tool.execute(**tool_call.arguments)
                return ToolResult(tool_call_id=tool_call.id, content=output)
            except MCPAuthRequired as e:
                # F5 L4 (A10): MCP tool requires user re-authentication.
                # Translate the control-flow signal into a ToolResult with
                # ``metadata.is_auth_required=True`` so the L3 step loop's
                # auth-required check fires (defers remaining tool calls and
                # surfaces the Login-required affordance to chat UI).
                return ToolResult(
                    tool_call_id=tool_call.id,
                    content="<auth required>",
                    metadata={
                        "is_auth_required": True,
                        "source_id": e.source_id,
                        "source_name": e.source_name,
                        "resource_metadata_url": e.resource_metadata_url,
                        "tool_call_id": tool_call.id,
                        "consent_url": e.consent_url,
                    },
                )
            except Exception as e:
                return ToolResult(
                    tool_call_id=tool_call.id,
                    content=f"[error] Tool execution failed: {e}",
                    is_error=True,
                )
        finally:
            current_tool_call_id.reset(token)

    def reset(self) -> None:
        """Reset messages to the system prompt and clear pause state."""
        self.messages = [Message.system(self.system_prompt)]
        # F5 L3: clear pause state alongside messages — otherwise a
        # subsequent ``step`` would see stale ``_deferred_tool_calls``
        # before its own initialization clobbers it.
        self._deferred_tool_calls = None
        self._remaining_iterations = 0
        # F10 L1: clear visibility filter so the next step starts blind.
        # Use .clear() (in-place mutation) NOT re-assignment — the same
        # containers may be referenced by the stub tools' closure-captured
        # _on_match callbacks; re-assignment would orphan those references.
        self._loaded_schemas.clear()
        self._loaded_tool_names.clear()
