"""DM-pairing prefix validator.

M10 F06 L2: parses the operator-shared pairing convention
``PAIR <code> <message>`` from an inbound envelope's text. Single-
space separator; the code is the operator's pre-shared one-time
secret; the message is the cleaned text the agent will see.

Pure function — no I/O. Dispatcher (``connectors/_inbound``) consults
on ``NeedsPairing`` outcomes; the function returns ``(success,
cleaned_text)`` so the dispatcher can branch.
"""

from __future__ import annotations

_PAIR_PREFIX = "PAIR "


def _validate_pairing_prefix(text: str, code: str) -> tuple[bool, str]:
    """Check ``text`` for a ``PAIR <code> <rest>`` prefix.

    Returns ``(True, cleaned)`` if the prefix matches AND the code is
    non-empty (an empty code never matches; defends against an account
    whose pairing entry was malformed past validator scope). ``cleaned``
    is the text with the entire prefix stripped (including the trailing
    single space). Returns ``(False, text)`` on any mismatch — text
    unchanged.

    The PAIR keyword is case-sensitive; the code comparison is
    byte-equality (no normalization). Whitespace inside the code is
    not permitted (the prefix parser uses single-space separators).
    """
    if not code:
        return False, text
    if not text.startswith(_PAIR_PREFIX):
        return False, text
    remainder = text[len(_PAIR_PREFIX) :]
    expected = code + " "
    if not remainder.startswith(expected):
        return False, text
    cleaned = remainder[len(expected) :]
    return True, cleaned
