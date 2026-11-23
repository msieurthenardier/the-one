"""The secret guard for proposals (M36 F2 L3, DD9).

``propose_change`` runs :func:`check` on every string in a proposal's changes, after the shape
accepts it and before anything is recorded. A stored secret value or a key-shaped string is
refused, so a key never reaches the proposals table, the card, or the approval path. The
refusal is one fixed sentence that never echoes the value; nothing here logs a value.

Two rules, one sentence:

- **A stored secret:** containment of any value from
  :func:`the_one.db.encryption_corpora.secret_leaves` (chosen per column), after trimming.
  The corpora are gathered once per call, never cached, so a rotation or edit applies at once
  (``strict=False``: a value that will not decrypt is skipped, and the key-shape rule still
  applies). A stored secret shorter than 8 characters is not searched.
- **A key-shaped string:** a common token prefix (``KEY_PREFIXES``) followed by at least
  ``KEY_PREFIX_MIN_TAIL`` key characters, or any run of at least ``KEY_MIN_LEN`` base64url
  characters with Shannon entropy of at least ``KEY_MIN_ENTROPY`` bits per character, or
  any run of at least ``HEX_KEY_MIN_LEN`` hex characters bounded by non-alphanumerics (the
  entropy rule cannot catch a hex-only key). A canonical hyphenated UUID is exempt from both
  rules; a bare 32-hex run is not a UUID and is refused. A long unbroken run of
  random-looking characters in an ordinary prompt can be a false positive; that is the
  accepted trade-off, and it includes a 40-character git SHA or a hex digest written into a
  prompt (the operator can enter it on the page, or shorten it).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from the_one.db.encryption_corpora import gather_corpora, secret_leaves

REFUSAL = (
    "That looks like a key or token. Leave it out of the proposal and tell the operator "
    "to enter it on the right page."
)

KEY_PREFIXES: tuple[str, ...] = (
    "sk-ant-",
    "sk-",
    "ghp_",
    "gho_",
    "github_pat_",
    "xox",
    "AKIA",
    "AIza",
    "glpat-",
    "hf_",
)
KEY_PREFIX_MIN_TAIL = 16
KEY_MIN_LEN = 32
KEY_MIN_ENTROPY = 4.0
# Hex-only keys cannot reach 4.0 bits per character (16 symbols cap at 4.0, and real ones
# fall below), so the entropy rule misses them: a bare run this long is refused outright.
HEX_KEY_MIN_LEN = 32

_PREFIX_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(p) for p in KEY_PREFIXES)
    + r")[A-Za-z0-9_\-]{%d,}" % KEY_PREFIX_MIN_TAIL
)
_RUN_RE = re.compile(r"[A-Za-z0-9_\-]{%d,}" % KEY_MIN_LEN)
_HEX_RUN_RE = re.compile(r"(?<![A-Za-z0-9])[0-9a-fA-F]{%d,}(?![A-Za-z0-9])" % HEX_KEY_MIN_LEN)
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)


def _strings(value: Any) -> list[str]:
    """Every string value in a nested structure (dict values, list items)."""
    if isinstance(value, str):
        return [value]
    out: list[str] = []
    if isinstance(value, dict):
        for v in value.values():
            out += _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out += _strings(v)
    return out


def _entropy(text: str) -> float:
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def looks_like_key(text: str, *, relaxed: bool = False) -> bool:
    """The key-shape rules (prefix + tail, or a long high-entropy run) on one string.

    ``relaxed`` skips the hex-run and entropy heuristics (never the prefix rule): for an
    address or command field, where a digest or an id in a path is not a key.
    """
    if _PREFIX_RE.search(text):
        return True
    if relaxed:
        return False
    scanned = _UUID_RE.sub(" ", text)
    if _HEX_RUN_RE.search(scanned):
        return True
    return any(_entropy(run) >= KEY_MIN_ENTROPY for run in _RUN_RE.findall(scanned))


async def check(
    conn: Any, enc: Any, changes: Any, *, relaxed: frozenset[str] = frozenset()
) -> str | None:
    """A refusal sentence when ``changes`` holds a stored secret or a key-shaped string.

    ``relaxed`` names stored keys of ``changes`` whose values skip the key-shape
    **heuristics** (the hex-run and entropy rules, see :func:`looks_like_key`): a kind's
    address and command fields (``Kind.relaxed_guard_keys``). The stored-secret containment
    and the token-prefix rule still apply to every value, and a key that is not named here
    keeps every rule.
    """
    texts = _strings(changes)
    if not texts:
        return None
    if isinstance(changes, dict) and relaxed:
        for key, value in changes.items():
            skip = key in relaxed
            if any(looks_like_key(t, relaxed=skip) for t in _strings(value)):
                return REFUSAL
    elif any(looks_like_key(t) for t in texts):
        return REFUSAL
    leaves = secret_leaves(await gather_corpora(conn, enc, strict=False))
    if leaves and any(leaf in t for t in texts for leaf in leaves):
        return REFUSAL
    return None
