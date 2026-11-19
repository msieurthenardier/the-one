"""The one naming rule for agents, model providers, knowledge bases and MCP servers.

Sortie 06 (safe names), DD1-DD3. A name is trimmed, then refused when it is empty,
holds a path separator (``/`` or ``\\``), is exactly ``.`` or ``..``, holds a control
or bidi-override character, or runs over 64 code points. Nothing else is restricted:
spaces, dots, accents and emoji stay legal.

This is a leaf module (stdlib only) called at the API write boundaries, never from
the pydantic models, so a stored legacy name still loads and can be repaired.
"""

import unicodedata

MAX_NAME_LENGTH = 64

EMPTY = "Enter a name."
SEPARATOR = "A name can't contain / or \\."
DOTS = "A name can't be . or .."
CONTROL = "A name can't contain control characters."
TOO_LONG = f"A name can be at most {MAX_NAME_LENGTH} characters."
SAME_AS_CURRENT = "The new name is the same as the current name."
NAME_CONFLICT_AGENT = "An agent with this name already exists."
NAME_CONFLICT_SECRET = "A secret with this name already exists."

# U+202A-U+202E (embedding/override) and U+2066-U+2069 (isolates): not Cc, but they
# reorder how a name is drawn.
_BIDI_CONTROLS = frozenset(chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


class NameRuleError(ValueError):
    """A name broke the rule; ``message`` is the one plain sentence to show."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def check_name(value: object) -> str:
    """Return ``value`` trimmed, or raise :class:`NameRuleError`."""
    if not isinstance(value, str):
        raise NameRuleError(EMPTY)
    stripped = value.strip()
    if not stripped:
        raise NameRuleError(EMPTY)
    if "/" in stripped or "\\" in stripped:
        raise NameRuleError(SEPARATOR)
    if stripped in (".", ".."):
        raise NameRuleError(DOTS)
    if any(unicodedata.category(c) == "Cc" or c in _BIDI_CONTROLS for c in stripped):
        raise NameRuleError(CONTROL)
    if len(stripped) > MAX_NAME_LENGTH:
        raise NameRuleError(TOO_LONG)
    return stripped


GLEEPGLORP_AGENT_NAME = "GleepGlorp"
RESERVED_AGENT_NAMES = frozenset({"default", "gleepglorp"})  # casefolded


def is_reserved_agent_name(name: object) -> bool:
    """True when ``name`` is, in any case, a name no stored agent may hold."""
    return isinstance(name, str) and name.strip().casefold() in RESERVED_AGENT_NAMES


def check_agent_name(value: object) -> str:
    """:func:`check_name`, then refuse the reserved agent names (any case)."""
    stripped = check_name(value)
    if stripped.casefold() == "gleepglorp":
        raise NameRuleError(
            f"“{stripped}” is the name of the built-in assistant. Choose another name."
        )
    if stripped.casefold() == "default":
        raise NameRuleError(f"“{stripped}” is a reserved name. Choose another name.")
    return stripped


def name_rule_detail(message: str, loc: str = "name") -> list[dict]:
    """A 422 body shaped like pydantic's, so the client maps it to the field."""
    return [{"type": "name_rule", "loc": [loc], "msg": message}]


_FALLBACK = {
    "agent": "Renamed agent",
    "provider": "Renamed provider",
    "knowledge_base": "Renamed knowledge base",
    "mcp_source": "Renamed MCP server",
}


def repair_name(value: str, *, kind: str, taken: set[str] | frozenset[str]) -> str:
    """Return a name that passes :func:`check_name` and is not in ``taken``.

    Sortie 06 DD12, used by the startup repair. Separators become spaces, so do
    whitespace controls (tab, newline); other control and bidi characters are
    deleted. Runs of whitespace collapse, the result is trimmed, cut to 64
    code points and trimmed again; an empty, ``.`` or ``..`` result becomes the
    kind's fallback. A collision with ``taken`` (compared by ``casefold``)
    appends `` 2``, `` 3``, ... to a base shortened to keep the whole within 64.
    """
    chars = []
    for c in value:
        if c in "/\\" or (unicodedata.category(c) == "Cc" and c.isspace()):
            chars.append(" ")
        elif unicodedata.category(c) == "Cc" or c in _BIDI_CONTROLS:
            continue
        else:
            chars.append(c)
    base = " ".join("".join(chars).split())
    base = base[:MAX_NAME_LENGTH].strip()
    if base in ("", ".", ".."):
        base = _FALLBACK[kind]
    used = {t.casefold() for t in taken}
    candidate = base
    n = 1
    while candidate.casefold() in used:
        n += 1
        suffix = f" {n}"
        candidate = base[: MAX_NAME_LENGTH - len(suffix)].rstrip() + suffix
    return candidate
