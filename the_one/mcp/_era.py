"""Per-source protocol-era memory (Mission 29 Flight 2, DD2).

A leaf module: stdlib only, nothing from ``the_one`` (so importing it never
pulls in ``the_one.mcp.oauth``). It holds two process-wide, in-memory maps (a
restart re-discovers): ``source_id -> protocol revision``, and (sortie 19, DD3)
``source_id -> count of consecutive no-answer fallbacks``, so a fallback caused by a
discover probe that got no answer is remembered only the second time in a row
(``record_result``). ``forget_era`` clears both.

``MCPClient.connect`` reads the map through ``era_for`` and passes the result to
``_negotiate.negotiate`` as ``remembered``; ``remember_era`` and ``forget_era`` are
called from the connect path, source update, delete, Reset connection and the
mid-use failure paths. The map is process-global and unlocked, which is safe only
because there is a single asyncio event loop.
"""

from __future__ import annotations

_ERAS: dict[str, str] = {}

# Consecutive "no answer" fallbacks per source (sortie 19, DD3). A fallback caused by
# a discover probe that got no answer is remembered only the second time in a row, so
# one slow start does not pin the source to the older protocol for the whole run.
_NO_ANSWER_COUNT: dict[str, int] = {}
_NO_ANSWER_REMEMBER_AT = 2


def era_for(source_id: str) -> str | None:
    """The revision last negotiated for ``source_id``, or None."""
    return _ERAS.get(source_id)


def remember_era(source_id: str, version: str) -> None:
    """Record the revision ``source_id`` connected on."""
    _ERAS[source_id] = version


def record_result(source_id: str, version: str, *, no_answer: bool) -> None:
    """Record a connect's result (the client's call, in place of ``remember_era``).

    A no-answer fallback raises the source's count; below 2 it also clears any
    remembered revision (the count is kept), at 2 the revision is remembered. Any
    other result resets the count and remembers the revision as ``remember_era`` does.
    """
    if not no_answer:
        _NO_ANSWER_COUNT.pop(source_id, None)
        _ERAS[source_id] = version
        return
    count = _NO_ANSWER_COUNT.get(source_id, 0) + 1
    _NO_ANSWER_COUNT[source_id] = count
    if count >= _NO_ANSWER_REMEMBER_AT:
        _ERAS[source_id] = version
    else:
        _ERAS.pop(source_id, None)


def forget_era(source_id: str) -> None:
    """Drop the memory and the no-answer count for ``source_id`` (a no-op when absent)."""
    _ERAS.pop(source_id, None)
    _NO_ANSWER_COUNT.pop(source_id, None)


def _clear_for_test() -> None:
    """Empty both maps (autouse test fixture only)."""
    _ERAS.clear()
    _NO_ANSWER_COUNT.clear()
