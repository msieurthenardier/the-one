from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable

from the_one.agent._context import current_tool_call_id
from the_one.agent._governor import govern_tool_content, governor_defaults
from the_one.db.codec import truncate_for_event
from the_one.llm.base import (
    ContentBlock,
    LLMProvider,
    Message,
    Role,
    TokenUsage,
    ToolCall,
    ToolResult,
)
from the_one.mcp.errors import MCPAuthRequired
from the_one.secret_store.runtime import WITHHELD_MESSAGE, Prepared, SecretMaskError, SecretResolver
from the_one.tools.base import ToolRegistry

_TOOL_CALL_TIMEOUT_ENV = "THE_ONE_TOOL_CALL_TIMEOUT_SECONDS"
_TOOL_CALL_TIMEOUT_DEFAULT = 120
_TOOL_CALL_TIMEOUT_FLOOR = 1


def _get_tool_call_timeout() -> float:
    """Return the per-tool-call timeout in seconds.

    Read at call time so monkeypatching ``os.environ`` in tests is
    effective without reloading the module.  Bad values (non-numeric,
    below the floor) fall back to the default; a floor of 1 s prevents
    0/negative timeouts.

    DD2 / Leg 2: env ``THE_ONE_TOOL_CALL_TIMEOUT_SECONDS`` (default 120).
    Lives in the agent layer — NOT imported from app.py to avoid an
    import cycle.
    """
    raw = os.environ.get(_TOOL_CALL_TIMEOUT_ENV, "")
    if raw:
        try:
            value = float(raw)
            return max(value, float(_TOOL_CALL_TIMEOUT_FLOOR))
        except ValueError:
            pass
    return float(_TOOL_CALL_TIMEOUT_DEFAULT)


def _executed_key(tc: ToolCall) -> tuple[str, str]:
    """Turn-local redundancy key for a tool call (M16 F03 L09, #105).

    Keyed on the call's **raw** ``tc.arguments`` (NOT post-positional-binding):
    a recovered gemma call is e.g. ``{"__positional_args__": ["echo hi"]}`` at
    this point — ``bind_positional_args`` runs later inside ``_execute_tool``
    and does NOT mutate the ToolCall, so each degraded re-emission recovers to
    the identical raw shape and the key matches across iterations. The
    ``sort_keys=True`` canonicalization makes the compare order-insensitive
    (DD-A). A freshly synthesized re-emission carries a different
    ``tool_call_id``, so the map keys on (name, args) rather than id.
    """
    return (tc.name, json.dumps(tc.arguments, sort_keys=True))


def _synthesize_closing(redundant: list[tuple[str, str, bool]]) -> str:
    """Render a non-empty closing message from already-obtained tool results.

    M16 F03 L09 (#105) — DD-C. ``redundant`` is a list of
    ``(tool_name, result_content, is_error)`` triples for the redundant calls
    whose results were captured earlier this turn (from the executed-map). The
    degraded model produced neither a new call nor closing text; this surfaces
    the prior result(s) deterministically so the user always gets an answer.

    A single result renders inline; multiple render as a compact list. Error
    results are marked as failures so the user isn't misled (the backstop
    guarantees *an* answer, not a successful one). Oversized result content is
    truncated via the shared codec projection cap (``truncate_for_event``) so a
    huge payload can't be dumped into the closing.
    """
    if len(redundant) == 1:
        name, content, is_error = redundant[0]
        body = truncate_for_event(content)
        if is_error:
            return f"The `{name}` call failed:\n{body}"
        return f"Done. The output of `{name}` was:\n{body}"

    lines = ["Done. Results so far:"]
    for name, content, is_error in redundant:
        body = truncate_for_event(content)
        label = "failed" if is_error else "output"
        lines.append(f"- `{name}` {label}:\n{body}")
    return "\n".join(lines)


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
# Mission 23 Flight 1 (backend-removal leg): the F4 (M10) baseline
# carve-out that pre-loaded `send_to_platform_channel`'s schema for
# connector-attached agents was removed along with the connector package
# and the send tool itself (DD-4) — search_tools is now the sole
# discovery path for every non-`continue` tool, no exceptions.
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
        degraded_system_prompt: str | None = None,
        secrets: SecretResolver | None = None,
    ) -> None:
        # Sortie 10 DD7 (owner-approved touch of the frozen loop): the secrets hook.
        # ``None`` keeps today's behaviour exactly.
        self._secrets = secrets
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        # The tool-free twin of ``system_prompt`` (same persona/rules/notes/date on
        # the tool-free platform prompt), sent instead of it when the model has no
        # native tool support. ``None`` -> ``system_prompt`` is sent verbatim.
        self.degraded_system_prompt = degraded_system_prompt
        self.max_iterations = max_iterations
        self.messages: list[Message] = [Message.system(system_prompt)]
        # F5 L3: pause/resume state (in-memory only; not persisted —
        # see class docstring). Set by ``step``; consumed by
        # ``resume_after_auth``.
        self._deferred_tool_calls: list[ToolCall] | None = None
        self._remaining_iterations: int = 0
        # Public: True only when the last turn ended because the iteration
        # budget ran out (the ``while`` in ``_run_iterations`` ended with no
        # ``return``). Cleared at the entry of ``step``, ``resume_after_auth``
        # and ``reset``; set before the generator returns, so a consumer
        # reading it after its ``async for`` sees it.
        self.stopped_at_step_limit: bool = False
        # F10 L1: visibility filter. SHARED CONTAINERS with the factory-
        # constructed search-stub tools — mutations from those tools land
        # in these containers; _compute_visible_schemas reads them.
        # Defaults to fresh empty containers if omitted (backward-compat
        # for non-factory Agent construction sites, e.g. tests).
        self._loaded_schemas: list[dict] = loaded_schemas if loaded_schemas is not None else []
        self._loaded_tool_names: set[str] = (
            loaded_tool_names if loaded_tool_names is not None else set()
        )
        # DD-5 (Mission 23 Flight 3 Leg 2): capture the factory's baseline-
        # visibility seed (e.g. the send-to-platform-channel carve-out) on
        # instance state — copies, since the live containers above mutate
        # as search_tools matches land. reset() has no memory of any seed
        # otherwise, so it re-extends from these on every reset.
        self._seed_schemas: list[dict] = list(self._loaded_schemas)
        self._seed_tool_names: set[str] = set(self._loaded_tool_names)

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
        user_input: str | list[ContentBlock],
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
        on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None,
    ) -> AsyncIterator[Message]:
        """Process a user message through the agent loop.

        Yields each assistant/tool message as it's produced.

        ``on_chunk``: optional async callback invoked once per content chunk
        during streaming. Callers that omit ``on_chunk`` get the original
        Message-yielding semantics; chunks fan out internally but only the
        synthesised final ``Message`` flows up via ``yield``.

        ``on_usage``: F7 L04 — optional async callback invoked when a
        ``StreamChunk`` carries an interim ``usage`` payload (chunk.usage is
        not None AND chunk.is_final is False). Fires ONLY for interim
        emissions so callers can broadcast progressive telemetry; final-
        chunk usage is intentionally skipped here because the caller's
        existing final-usage broadcast path (see ``_process_and_broadcast``
        in the web layer) handles end-of-step accumulation. Back-compat:
        providers that never emit interim usage just never fire the
        callback. Defaults to None.
        """
        self.stopped_at_step_limit = False
        self.messages.append(Message.user(user_input))
        # F5 L3: clear stale pause state at the start of a new step and
        # re-prime the iteration budget. ``_run_iterations`` decrements
        # ``_remaining_iterations`` at the top of each iteration body.
        self._deferred_tool_calls = None
        self._remaining_iterations = self.max_iterations
        async for msg in self._run_iterations(on_chunk, on_usage):
            yield msg

    async def _run_iterations(
        self,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
        on_usage: Callable[[TokenUsage], Awaitable[None]] | None = None,
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
        # M16 F03 L08C (#105): if the model can't accept a native tools= array
        # (e.g. Ollama Gemma — Ollama 400s if tools are offered), the degraded
        # path runs as a CHAT-ONLY conversation: a tool-free system prompt
        # (the tool-free platform prompt, no catalog/protocol) is injected and recovery is
        # gated OFF at the provider level so spontaneously-emitted tool_code
        # blocks pass through verbatim as assistant text. The wire tools= stays
        # None. Studio surfaces the degraded model via the red "no tools"
        # capability chip on the model selector.
        supports_tools = await self.llm.supports_tools()

        # M16 F03 L09 (#105) — CP4 backstop. Turn-local executed-map for the
        # DEGRADED path only: (name, canonical-json(raw args)) →
        # (ToolResult content, is_error) captured after a successful, non-paused
        # dispatch. Used to detect the gemma re-emission loop (same call
        # re-emitted, terminating with an empty message) and synthesize a
        # closing answer. Reset per _run_iterations entry. NOT consulted on the
        # capable path (DD-D).
        executed: dict[tuple[str, str], tuple[str, bool]] = {}

        while self._remaining_iterations > 0:
            self._remaining_iterations -= 1  # F5 L3: consume one iteration up-front

            # F10 L1: per-iteration visibility filter recompute so that
            # search-driven mutations to _loaded_schemas from iteration N
            # appear in iteration N+1's tools= array.
            #
            # M16 F03 L08C: on the degraded path build an EPHEMERAL message list
            # that REPLACES messages[0] (always the system prompt) with the
            # tool-free chat prompt (``degraded_system_prompt``). self.messages
            # is NOT mutated. The wire tools= stays None on this path.
            if supports_tools:
                tool_schemas = self._compute_visible_schemas()
                request_messages = self.messages
            else:
                tool_schemas = []
                request_messages = self._build_degraded_messages()

            accumulated_text, final_chunk = await self._stream_response(
                messages=request_messages,
                tool_schemas=tool_schemas,
                on_chunk=on_chunk,
                on_usage=on_usage,
            )

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

            # M16 F03 L09 (#105): which calls to dispatch this iteration. On
            # the CAPABLE path this stays BYTE-IDENTICAL to pre-leg behavior —
            # dispatch all of response.tool_calls; the backstop does not run
            # (DD-D: a capable model may legitimately re-poll changing state,
            # e.g. shell("date"), so short-circuiting on a stale result would
            # be wrong). On the DEGRADED path, partition into new vs redundant
            # (already-dispatched-this-turn) and run the all-redundant backstop.
            if supports_tools:
                to_dispatch = response.tool_calls
            else:
                new = [tc for tc in response.tool_calls if _executed_key(tc) not in executed]
                if not new:
                    # Every call this iteration is a redundant re-emission of a
                    # call whose result we already hold — the degraded loop is
                    # stuck (DD-C / DD-C2). Gather the stored results to surface.
                    redundant = [
                        (tc.name, *executed[_executed_key(tc)]) for tc in response.tool_calls
                    ]
                    if not response.content.strip():
                        # DD-C: no new call AND no closing text → REPLACE the
                        # empty terminal message in-place with a synthesized
                        # closing. ``response is self.messages[-1]`` here
                        # (nothing dispatched/appended since the append above),
                        # so replacing avoids persisting an empty assistant
                        # message that still carries orphaned tool_calls.
                        closing = _synthesize_closing(redundant)
                        self.messages[-1] = Message.assistant(content=closing)
                        yield self.messages[-1]
                        return
                    # DD-C2: no new call but the model DID answer with text.
                    # The response (already appended + yielded) IS the answer;
                    # clear its now-undispatched tool_calls so replay emits no
                    # orphaned tool_call events, then return without dispatching.
                    self.messages[-1].tool_calls = []
                    return
                to_dispatch = new

            # F5 L3: dispatch tool calls through the helper; if any tool
            # returns ``metadata.is_auth_required``, the helper captures
            # current + remaining tool calls into ``_deferred_tool_calls``
            # and returns; we then exit so the WebSocket layer can
            # broadcast the auth_required event without a follow-up
            # ``done``.
            async for tool_msg in self._dispatch_tool_calls(to_dispatch):
                yield tool_msg

            if self._deferred_tool_calls is not None:
                return  # paused — exit; remaining iterations preserved

            # M16 F03 L09 (#105): record this dispatch's results into the
            # turn-local executed-map (DEGRADED path only — the map is never
            # consulted on the capable path). ONLY after a successful,
            # non-paused dispatch (the auth-pause return above guards this), so
            # a paused call is never treated as redundant on resume. Match each
            # dispatched real call to its just-appended Role.TOOL result by
            # tool_call_id; skip the ``continue`` virtual signal (no real
            # result to surface).
            if not supports_tools:
                results_by_id = {
                    m.tool_result.tool_call_id: m.tool_result
                    for m in self.messages
                    if m.role == Role.TOOL and m.tool_result is not None
                }
                for tc in to_dispatch:
                    if tc.name == "continue":
                        continue
                    result = results_by_id.get(tc.id)
                    if result is not None:
                        executed[_executed_key(tc)] = (result.content, result.is_error)

        # The ``while`` ended with no ``return``: the budget ran out (also the
        # case for a zero budget on entry). Set before the generator returns.
        self.stopped_at_step_limit = True

    async def _stream_response(
        self,
        *,
        messages: list[Message],
        tool_schemas: list[dict],
        on_chunk: Callable[[str], Awaitable[None]] | None,
        on_usage: Callable[[TokenUsage], Awaitable[None]] | None,
    ) -> tuple[str, object | None]:
        """Stream one LLM response, fanning chunks out to the callbacks.

        Factored out so the tool-capable branch (``messages=self.messages``,
        the visible-schema array) and the degraded branch
        (``messages=<ephemeral list>``, ``tool_schemas=[]`` → ``tools=None``)
        share the exact same chunk/usage handling. Returns the accumulated
        text and the final ``StreamChunk`` (or ``None`` if the stream produced
        no final chunk).
        """
        accumulated_text = ""
        final_chunk = None
        async for chunk in self.llm.stream(
            messages=messages,
            tools=tool_schemas or None,
        ):
            if chunk.content:
                accumulated_text += chunk.content
                if on_chunk:
                    await on_chunk(chunk.content)
            # F7 L04: interim-only usage emission. Final-chunk usage is
            # handled by the existing per-step accumulation path in the
            # caller (avoids double-emission with the final usage_event
            # broadcast in _process_and_broadcast). Cycle-1 [high]: gate
            # on `chunk.usage is not None AND not chunk.is_final`.
            if chunk.usage is not None and not chunk.is_final and on_usage is not None:
                await on_usage(chunk.usage)
            if chunk.is_final:
                final_chunk = chunk
                break
        return accumulated_text, final_chunk

    def _build_degraded_messages(self) -> list[Message]:
        """Build the ephemeral chat-only request message list for non-tool models.

        M16 F03 L08C (#105): for a non-tool-capable model (``supports_tools()=False``),
        REPLACE ``messages[0]`` (always the system prompt) with a tool-free chat prompt
        — the tool-free platform prompt with no catalog, no ``tool_code`` format spec, no
        ``continue``-tool turn semantics. ``self.messages`` is left untouched.

        Recovery is gated OFF at the provider level (OllamaProvider.complete() /
        .stream() gate ``_recover_into_tool_calls`` on ``supports_tools()``), so
        even if the model spontaneously emits a ``tool_code`` fence the block passes
        through verbatim as assistant text rather than being parsed and dispatched.

        The tool-free prompt is built at agent-build time (``degraded_system_prompt``);
        when it is unset ``system_prompt`` is sent verbatim. No prefix recovery.

        Updates Flight 3 DD2 / DD-G: the degraded path is now conversational-only;
        the Leg-09 backstop (partition/synthesize logic below) becomes harmless dead code
        on this path — a non-tool model's recovered tool_calls is always empty, so the
        ``new`` set is always empty and the backstop never fires. Left in place as it
        still validates the loop logic for structured-tool_calls inputs in tests. See
        flight-log for the debrief cleanup note.
        """
        chat_system = (
            self.degraded_system_prompt
            if self.degraded_system_prompt is not None
            else self.system_prompt
        )
        return [Message.system(chat_system), *self.messages[1:]]

    async def _dispatch_tool_calls(self, tcs: list[ToolCall]) -> AsyncIterator[Message]:
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

            # F5 L3: pause/resume check. Capture current + remaining tool
            # calls so ``resume_after_auth`` can re-dispatch them in order
            # (slice-from-current-index pattern works at index 0 too —
            # covered by A8b). The state MUST be set BEFORE the yield:
            # consumers (the WebSocket layer) stop iterating as soon as they
            # see the auth-required message, so the generator never resumes
            # past the yield and code placed after it would never run.
            paused = bool(result.metadata and result.metadata.get("is_auth_required"))
            if paused:
                self._deferred_tool_calls = list(tcs[i:])
            yield tool_msg
            if paused:
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
        self.stopped_at_step_limit = False
        if self._deferred_tool_calls is None:
            return  # A7 no-op

        deferred = self._deferred_tool_calls
        self._deferred_tool_calls = None  # consumed before re-dispatch

        # The pause left an auth-required placeholder tool message in the
        # history for each deferred call it paused on. The re-dispatch below
        # appends the real result, and providers reject two tool results for
        # one tool_use id, so drop the placeholders first. Match on BOTH the
        # call id and the is_auth_required metadata so a real result is never
        # removed.
        deferred_ids = {tc.id for tc in deferred}
        self.messages[:] = [
            m
            for m in self.messages
            if not (
                m.role == Role.TOOL
                and m.tool_result is not None
                and m.tool_result.tool_call_id in deferred_ids
                and (m.tool_result.metadata or {}).get("is_auth_required")
            )
        ]

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

    def _govern(self, content: str, direction: str = "head") -> str:
        """Bound a tool-result string to the model's context-budget (DD1).

        M16 F08 L01: the single governance chokepoint. ``self.llm.bytes_per_token``
        and ``self.llm.max_context_tokens`` (resolved on the first ``stream()``
        before any tool dispatch; sane class-attr fallback otherwise) feed the
        pure ``govern_tool_content`` helper. Env-overridable fraction/floor/
        ceiling are read at call time via ``governor_defaults()``.

        Both LLM values are read with ``getattr`` defaults so a custom provider
        (or a minimal test double) that doesn't set them can't crash tool
        dispatch — they fall back to the ``LLMProvider`` base defaults, and the
        helper itself floors a missing/absurd ``max_context_tokens`` (LOW-2).
        """
        fraction, floor, ceiling = governor_defaults()
        return govern_tool_content(
            content,
            getattr(self.llm, "max_context_tokens", None),
            fraction=fraction,
            floor=floor,
            ceiling=ceiling,
            direction=direction,  # type: ignore[arg-type]
            bytes_per_token=getattr(self.llm, "bytes_per_token", 4.0),
        )

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        # F6 L3: bind tool_call_id into the per-task ContextVar so the
        # MCP pool's _entry_worker (and the OAuth handlers it wires)
        # can attach the originating tool_call_id to any auth_required
        # broadcast. Reset in finally — the inner try/except blocks
        # handle MCPAuthRequired translation (F5 L4) and generic
        # exception fall-through, both of which return through the
        # outer finally.
        token = current_tool_call_id.set(tool_call.id)
        prepared: Prepared | None = None
        try:
            try:
                tool = self.tools.get(tool_call.name)
                args = tool.bind_positional_args(tool_call.arguments)
                if self._secrets is not None:
                    # Sortie 10 DD7: fill {{secret:key}} into a copy, or refuse the call.
                    prepared = await self._secrets.prepare(tool_call.name, args)
                    if prepared.refusal is not None:
                        return ToolResult(
                            tool_call_id=tool_call.id, content=prepared.refusal, is_error=True
                        )
                    args = prepared.args
                # DD2 / Leg 2: bound every tool invocation with a configurable
                # ceiling so no single tool call can wedge a turn indefinitely.
                # ``asyncio.wait_for`` cancels the wrapped coroutine on expiry;
                # a tool that swallows ``CancelledError`` may not return promptly
                # — the guarantee is best-effort on tool cooperation.
                timeout = _get_tool_call_timeout()
                output = await asyncio.wait_for(tool.execute(**args), timeout=timeout)
                if prepared is not None:
                    output = prepared.safe_mask(output)  # before the governor truncates
                # M16 F08 L01 (DD1 / LOW-3): govern the normal-path output so no
                # single tool result can consume a disproportionate share of the
                # context window. Direction is tool-declared (head for prose/
                # pages/files; tail for shell/exec so the [exit code]/stderr tail
                # survives). The auth-required sentinel below is NOT governed.
                output = self._govern(output, tool.truncation_direction)
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
            except SecretMaskError:
                return ToolResult(
                    tool_call_id=tool_call.id, content=WITHHELD_MESSAGE, is_error=True
                )
            except asyncio.TimeoutError:
                # DD2 / Leg 2: tool exceeded the configured ceiling.
                # Return a tool-error so the loop records the result and
                # terminates the turn cleanly with ``done`` semantics.
                # The outer ``finally`` still resets ``current_tool_call_id``.
                text = f"tool {tool_call.name} timed out after {timeout:.0f}s"
                try:
                    if prepared is not None:
                        text = prepared.safe_mask(text)
                except SecretMaskError:
                    return ToolResult(
                        tool_call_id=tool_call.id, content=WITHHELD_MESSAGE, is_error=True
                    )
                return ToolResult(
                    tool_call_id=tool_call.id, content=self._govern(text), is_error=True
                )
            except Exception as e:
                # M16 F08 L01: govern the error string too — a tool may surface a
                # large exception payload (e.g. an embedded response body).
                text = f"[error] Tool execution failed: {e}"
                try:
                    if prepared is not None:
                        text = prepared.safe_mask(text)
                except SecretMaskError:
                    return ToolResult(
                        tool_call_id=tool_call.id, content=WITHHELD_MESSAGE, is_error=True
                    )
                return ToolResult(
                    tool_call_id=tool_call.id, content=self._govern(text), is_error=True
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
        self.stopped_at_step_limit = False
        # F10 L1: clear visibility filter so the next step starts blind.
        # Use .clear() (in-place mutation) NOT re-assignment — the same
        # containers may be referenced by the stub tools' closure-captured
        # _on_match callbacks; re-assignment would orphan those references.
        self._loaded_schemas.clear()
        self._loaded_tool_names.clear()
        # DD-5: re-seed the baseline carve-out (e.g. the send tool) from
        # the __init__-captured seed. Also in-place (.extend()/.update()),
        # for the same closure-capture reason as the .clear() calls above —
        # this is the "surviving a reset" guarantee the leg pins.
        self._loaded_schemas.extend(self._seed_schemas)
        self._loaded_tool_names.update(self._seed_tool_names)

    async def aclose(self) -> None:
        """Release the LLM provider's persistent HTTP client.

        F05 L01: idempotent — a ``_closed`` guard prevents double-close.
        Delegates to ``LLMProvider.aclose()``; the base implementation is
        a no-op (providers without a persistent client inherit it).
        Providers that hold a live ``httpx.AsyncClient`` (Anthropic, OpenAI)
        override it. MCP tool handles are pool-owned and NOT closed here —
        the MCP pool has its own TTL reaper.
        """
        if getattr(self, "_closed", False):
            return
        self._closed = True
        await self.llm.aclose()
