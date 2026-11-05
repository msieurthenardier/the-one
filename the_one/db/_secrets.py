"""The secrets prompt layer (sortie 10, DD8).

(Lives under ``the_one.db`` beside ``_rules.py`` and ``_notes.py`` so it can be
imported without the ``the_one.agent`` package cycle. It must NOT import
``the_one.agent``.)

The layer names an agent's granted secrets by placeholder, never by value: it holds
keys, secret names, descriptions and allowed tools only, so building it needs no
decryption. It is part of the tool-capable prompt only.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

SECRETS_HEADING = (
    "Secrets you can use. Write a secret's placeholder, such as {{secret:key}}, inside a "
    "tool argument; the real value is filled in when the tool runs and you never see it. "
    "Tool output shows [secret:key] where a value appears. Each key works only in the "
    "tools listed beside it. Never ask the person for a secret's value."
)

_CLOSE_RE = re.compile(r"</(secrets)", re.IGNORECASE)


def _neutralise(text: str) -> str:
    """Keep operator text from closing the block or breaking a line."""
    return _CLOSE_RE.sub(r"<\\\1", " ".join(text.split()))


def render_secrets_block(entries: Sequence[tuple[str, str, str, Sequence[str]]]) -> str:
    """``entries`` is ``[(key, secret_name, description, allowed_tools)]`` in prompt
    order (secrets by name, keys by position). Returns ``""`` for none."""
    if not entries:
        return ""
    lines = []
    for key, name, description, tools in entries:
        label = _neutralise(name)
        if description.strip():
            label += f": {_neutralise(description)}"
        listed = ", ".join(tools) if tools else "none"
        lines.append(f"{{{{secret:{key}}}}} - {label} (tools: {listed})")
    body = "\n".join(lines)
    return f"{SECRETS_HEADING}\n\n<secrets>\n{body}\n</secrets>"
