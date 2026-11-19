"""The mask shape of a returned secret and its recogniser (a leaf module).

Moved out of ``the_one/interfaces/web/api.py`` so the agent write checks
(``the_one/agent/write_checks.py``) can recognise a round-tripped mask without
importing the interface layer. ``api.py`` imports every name below under its old
underscore name. The emit helper (``_emit_mask`` in ``api.py``) and the recognise
shape here read the same constants, so they cannot drift (M11 F8 L3).
"""

from __future__ import annotations

import re
from typing import Any

MASK_PREFIX = "***"
MASK_TAIL_SEPARATOR = "..."
MASK_TAIL_LEN = 4

# Canonical "preserve existing stored value" sentinel for PUT payloads: the Studio
# UI emits this exact string for any secret field the operator did not touch.
MASKED_API_KEY_SENTINEL = "__MASKED__"

# Matches the exact output shape of ``_emit_mask``: ``MASK_PREFIX`` alone, or
# ``MASK_PREFIX + MASK_TAIL_SEPARATOR + 1 to MASK_TAIL_LEN characters``. Anchored on
# both sides so a real value that merely starts with ``***`` is not taken for a mask.
MASK_SHAPE_RE = re.compile(
    rf"^{re.escape(MASK_PREFIX)}({re.escape(MASK_TAIL_SEPARATOR)}.{{1,{MASK_TAIL_LEN}}})?$"
)


def looks_masked(value: Any) -> bool:
    """True if ``value`` is the ``__MASKED__`` sentinel or a mask-shape string.

    PUT handlers treat both as "preserve the stored value", so a client that
    round-trips a masked GET response never corrupts a stored secret with the mask
    text. Non-strings are never masked.
    """
    if not isinstance(value, str):
        return False
    if value == MASKED_API_KEY_SENTINEL:
        return True
    return bool(MASK_SHAPE_RE.match(value))
