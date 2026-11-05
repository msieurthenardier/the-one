"""Tools that can never receive a secret (sortie 10, DD3).

A tool that persists its arguments and later feeds them back to the model provider,
or that publishes them, would turn a substituted secret value into stored plaintext or
send it to other people. Those tools are refused when a secret's ``allowed_tools`` is
saved, and (leg 2) at run time even if a stored row somehow lists one.

Import rule: ``the_one.agent`` imports ``core``, and ``core`` will import this package,
so this module must not import ``the_one.agent`` at load. The notes and routine tool
names are imported lazily, inside the function that builds the set.
"""

from __future__ import annotations

from the_one.self_configuration.constants import SURFACE_TOOL_PREFIX

# The platform-channel sender publishes its text; the loop's two virtual tools carry the
# model's own arguments back into the conversation.
_FIXED_REFUSED: frozenset[str] = frozenset({"send_to_platform_channel", "continue", "search_tools"})

_cached: frozenset[str] | None = None


def refused_tool_names() -> frozenset[str]:
    """The exact refused names (the surface prefix is matched separately)."""
    global _cached
    if _cached is None:
        from the_one.agent.tool_names import NOTES_TOOL_NAMES, ROUTINE_TOOL_NAMES

        _cached = _FIXED_REFUSED | frozenset(NOTES_TOOL_NAMES) | frozenset(ROUTINE_TOOL_NAMES)
    return _cached


def is_refused_tool(name: str) -> bool:
    """Whether ``name`` stores or publishes what it receives."""
    return name.startswith(SURFACE_TOOL_PREFIX) or name in refused_tool_names()
