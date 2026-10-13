"""Per-source protocol-era memory (Mission 29 Flight 2, DD2).

A leaf module: stdlib only, nothing from ``the_one`` (so importing it never
pulls in ``the_one.mcp.oauth``). It holds a process-wide ``source_id ->
protocol revision`` map, in memory only; a restart re-discovers.

Leg 1 creates the module so the failure matrix's ``forget_era`` cells exist;
nothing reads or writes the map yet beyond that.
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
