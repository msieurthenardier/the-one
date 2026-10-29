"""Per-task context for agent dispatch.

Owns the canonical definitions of:

- ``current_chat_session_id``: identifier for the chat session whose
  agent is currently dispatching. Set by the WebSocket message handler
  in ``the_one.interfaces.web.app`` (``_spawn_message_processing`` and
  ``_resume_paused_session``) at message-processing entry; reset on
  exit via the token pattern.
- ``current_tool_call_id``: identifier for the specific tool call
  currently being dispatched. Set by ``Agent._execute_tool`` at
  function entry; reset in ``finally``.

Both ContextVars are read by ``the_one.mcp._pool._entry_worker`` at
pool-spawn time to route OAuth ``auth_required`` broadcasts to the
correct chat session and to attach the originating tool_call_id to
the broadcast payload (so the chat UI can correlate the
Login-required button to the specific tool call).

Cross-task inheritance: ``asyncio.create_task`` snapshots the parent
task's context at creation time. The pool worker task spawned via
``asyncio.create_task`` inside ``acquire`` inherits the
``current_chat_session_id`` and ``current_tool_call_id`` from the
calling tool dispatch. This is the F4 task-pinning trade-off:
the FIRST acquire of an ``(agent_name, source_id)`` key pins the
ContextVar values for the entry's lifetime; subsequent acquires
within idle TTL reuse the cached client whose OAuth provider was
built with the FIRST acquire's csid+tcid. F6 inherits this; cross-
session routing of the broadcast still depends on F5's "most-
recently-active session fallback" in OAuth handlers for the
warm-pool case.

Canonical home (this module) per the
``canonical-import + convenience-re-export`` convention
(``the_one/agents.md::Project Conventions``):
``the_one.interfaces.web.app`` re-exports ``current_chat_session_id``
for back-compat with F5's set-sites; future consumers in any layer
should import from here.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field

current_chat_session_id: ContextVar[str | None] = ContextVar(
    "current_chat_session_id", default=None
)
"""The chat session id whose agent is currently dispatching.

None when no chat session is active in the current task scope (e.g.
agent build invoked from CLI / REST / tests). Pool's
``_entry_worker`` reads this; when None, ``build_oauth_provider_for_source``
returns None (no provider — lazy 401 path surfaces at next
``call_tool`` which DOES have per-tool-dispatch context bound).
"""

current_tool_call_id: ContextVar[str | None] = ContextVar("current_tool_call_id", default=None)
"""The tool_call_id of the specific tool call currently being dispatched.

Set by ``Agent._execute_tool`` at function entry. Read by the OAuth
handlers' ``redirect_handler`` so the ``auth_required`` broadcast
payload carries the originating tool_call_id (for chat-UI
correlation of the Login-required button).

None when no tool call is currently dispatching (e.g. pool spawn
during agent build's ``MCPToolProvider.get_tools_for_agent`` call —
before any tool call has fired).
"""


@dataclass(frozen=True)
class TurnPeer:
    """The connector peer whose inbound message started the current turn."""

    platform: str
    connector_id: str | None
    peer_id: str
    peer_name: str | None


@dataclass
class TurnContext:
    """Mutable per-turn context set around ``agent.step`` (Mission 27 F2, DD5).

    Tools MUTATE this shared object (``writes += 1``) and never call
    ``current_turn.set()`` themselves: ``asyncio.wait_for`` runs a tool in a
    copied context, so a ``set`` inside a tool is lost while a mutation of the
    object is visible to the caller. ``session_id`` is the origin session for
    notes (it covers the REST path, which does not set
    ``current_chat_session_id``).

    EVERY new ``agent.step`` / ``resume_after_auth`` call site must set this
    (see ``the_one/agents.md`` "Agent notes").
    """

    peer: TurnPeer | None = None
    session_id: str | None = None
    writes: int = 0
    # M33 F2 L3 (DD7/DD8): the routine run this turn belongs to (None for an ordinary
    # turn), the sources it was flagged with, and the routine tools' own write budget.
    routine_id: str | None = None
    routine_name: str | None = None
    routine_sources: list[str] = field(default_factory=list)
    routine_writes: int = 0


current_turn: ContextVar[TurnContext | None] = ContextVar("current_turn", default=None)
"""The turn context for the step in progress; None outside a set site."""
