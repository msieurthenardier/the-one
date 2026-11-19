"""The server-turn seam: what code outside ``interfaces/`` needs from the web app.

The web app registers one host in its lifespan (``set_turn_host``); the routine runner and the
GleepGlorp proposal continuation reach it through ``get_turn_host()``. Nothing here imports
from ``interfaces`` (Mission 36 F2 L5, DD12; the Protocol moved here from ``routines/runner``).
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


class TurnHost(Protocol):
    """What a server-side turn starter needs from the web app."""

    async def get_or_restore(self, sid: str) -> tuple[Any | None, str]: ...

    async def create_web_session(self, agent_name: str, title: str) -> str: ...

    def spawn_turn(self, session: Any, prompt: str, turn_info: dict[str, Any]) -> asyncio.Task: ...

    def mark_silent_and_cancel(self, task: asyncio.Task) -> None: ...

    def discard_silent(self, task: asyncio.Task) -> None: ...

    def mirror_metadata(self, sid: str, key: str, value: Any) -> None: ...

    async def broadcast(self, sid: str, payload: dict[str, Any]) -> None: ...

    async def append_marked_message(
        self, session_id: str, text: str, marks: dict[str, Any]
    ) -> bool:
        """Append a marked USER message with no turn. ``False`` only when the chat is gone."""
        ...


_host: TurnHost | None = None


def set_turn_host(host: TurnHost | None) -> None:
    global _host
    _host = host


def get_turn_host() -> TurnHost | None:
    return _host
