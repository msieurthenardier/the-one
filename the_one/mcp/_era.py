"""Per-source protocol-era memory (Mission 29 Flight 2, DD2).

A leaf module: stdlib only, nothing from ``the_one`` (so importing it never
pulls in ``the_one.mcp.oauth``). It holds a process-wide ``source_id ->
protocol revision`` map, in memory only; a restart re-discovers.

``MCPClient.connect`` reads the map through ``era_for`` and passes the result to
``_negotiate.negotiate`` as ``remembered``; ``remember_era`` and ``forget_era`` are
called from the connect path, source update, delete, Reset connection and the
mid-use failure paths. The map is process-global and unlocked, which is safe only
because there is a single asyncio event loop.
"""

from __future__ import annotations

_ERAS: dict[str, str] = {}


def era_for(source_id: str) -> str | None:
    """The revision last negotiated for ``source_id``, or None."""
    return _ERAS.get(source_id)


def remember_era(source_id: str, version: str) -> None:
    """Record the revision ``source_id`` connected on."""
    _ERAS[source_id] = version


def forget_era(source_id: str) -> None:
    """Drop the memory for ``source_id`` (a no-op when absent)."""
    _ERAS.pop(source_id, None)


def _clear_for_test() -> None:
    """Empty the map (autouse test fixture only)."""
    _ERAS.clear()
