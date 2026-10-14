"""The platform prompt: the text the platform itself puts before every agent.

Built from ordered :class:`Section` objects so each part is nameable (the evals
measure them by section; Settings › Prompts will list them). Sections are
concatenated with NO separator inserted by the renderer: each section's text
carries its own leading whitespace, which is what lets the execution bullet sit
mid-way through the "Tool use:" block.

Two variants exist: the tool-capable prompt (``caps.tools``) and the tool-free
prompt a model without native tool support receives (M16 F03 L08C, #105: no
catalog, no ``continue`` semantics, so the model converses naturally).

Flight 2 leg 1b: this replaces the fixed ``BASE_PROMPT`` / ``CHAT_ONLY_PROMPT``
constants with byte-identical output. No condition is switched on yet: only
``caps.tools`` selects text. The other capability fields are carried for the
conditions that land in the next leg.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

_EXEC_TOOL_NAMES = frozenset({"shell", "python_exec"})
_KB_TOOL_PREFIX = "kb__"


@dataclass(frozen=True)
class Capabilities:
    """What an agent can do, as far as the platform prompt is concerned."""

    tools: bool = True
    knowledge: bool = True
    notes: bool = True
    rules: bool = True
    time_tool: bool = True
    exec_tools: bool = True

    @classmethod
    def all_on(cls) -> "Capabilities":
        return cls()


@dataclass(frozen=True)
class Section:
    """One named part of the platform prompt."""

    id: str
    title: str
    applies_when: str
    _applies: Callable[[Capabilities], bool]
    _text: Callable[[Capabilities], str]

    def applies(self, caps: Capabilities) -> bool:
        return self._applies(caps)

    def text(self, caps: Capabilities) -> str:
        return self._text(caps)


def _const(s: str) -> Callable[[Capabilities], str]:
    return lambda _caps: s


def _tools(caps: Capabilities) -> bool:
    return caps.tools


def _no_tools(caps: Capabilities) -> bool:
    return not caps.tools


def _exec_tools(caps: Capabilities) -> bool:
    return caps.tools and caps.exec_tools


def _always(_caps: Capabilities) -> bool:
    return True


_IDENTITY_TOOLS = """\
You are an AI agent with access to a set of tools. Use them to accomplish what the \
operator asks.
"""

# Knowledge-base phrases inside the tool-discovery text (Flight 2 leg 1c, DD3).
# Each has a with-knowledge form and a no-knowledge form written out as its own
# literal (never spliced), and both are pinned verbatim by tests.
KB_CATALOG = (
    "The catalog covers built-in tools (shell, file operations, web fetch, etc.), "
    "tools from any MCP servers attached to this agent, AND search tools for any "
    "knowledge bases attached to this agent \u2014 they all surface through this one tool. "
)
NO_KB_CATALOG = (
    "The catalog covers built-in tools (shell, file operations, web fetch, etc.) "
    "and tools from any MCP servers attached to this agent \u2014 they all surface "
    "through this one tool. "
)
KB_GROUPS = (
    "Results are grouped by source: `built-in: \u2026` for built-in tools, "
    "`mcp:<server>: \u2026` for MCP server tools, `kb:<name>: \u2026` for "
    "knowledge-base search tools. "
)
NO_KB_GROUPS = (
    "Results are grouped by source: `built-in: \u2026` for built-in tools and "
    "`mcp:<server>: \u2026` for MCP server tools. "
)
KB_EXAMPLES = 'search by intent ("issue tracker", "read a file", "http request", "internal docs")'
NO_KB_EXAMPLES = 'search by intent ("issue tracker", "read a file", "http request")'

_TD_HEAD = """
Tool discovery:
- At the start of each conversation, you have only `search_tools` and `continue` \
available.
- To use any other capability, call `search_tools` with a query describing what you \
need. """

_TD_AFTER_CATALOG = """Empty query lists everything; a specific query narrows results.
- """

_TD_AFTER_GROUPS = """Don't second-guess which catalog has what \u2014 just """

_TD_TAIL = """ and the right tools will surface regardless of where they come from.
- Matched tools are automatically added to your available toolset for the rest of \
this conversation. Once you've searched for a tool, you can call it by name on \
subsequent turns; no need to search again.
- New conversations start fresh with the baseline (just `search_tools` + \
`continue`). If the operator attached a new MCP server mid-session, you'll see it in \
your next session, not the current one.
"""


def _tool_discovery(caps: Capabilities) -> str:
    kb = caps.knowledge
    return (
        _TD_HEAD
        + (KB_CATALOG if kb else NO_KB_CATALOG)
        + _TD_AFTER_CATALOG
        + (KB_GROUPS if kb else NO_KB_GROUPS)
        + _TD_AFTER_GROUPS
        + (KB_EXAMPLES if kb else NO_KB_EXAMPLES)
        + _TD_TAIL
    )


_TOOL_USE_HEAD = """
Tool use:
- When an action is needed, take the action. Don't describe what you would do.
- Prefer the right tool for the job. Read files with the file-reading tool, not by \
asking the operator to paste them. Run commands with the shell tool, not by \
speculating about output."""

_EXECUTION = """
- Execution tools default to an isolated box with no access to the user's files or \
network; request host access only when the task concretely needs the user's real \
files or network."""

_TOOL_USE_TAIL = """
- On failure, try a different approach before giving up. State what failed and what \
you're trying next.
- Tool descriptions tell you what each tool does and when it applies. Read them.

Turn semantics:
- Each user message starts a turn. Within a turn you may call tools, see their \
results, and call more tools.
- When you still have work to do but want to think or act in another step, call the \
`continue` tool. It signals "give me another turn"; nothing more.
- When you're done, just respond with text. No `continue` call ends your turn.
"""

_IDENTITY_FREE = """\
You are an AI assistant. Respond directly and concisely to the user.
"""

_CLOSING = """
A persona, scope, or set of instructions may be appended below this base prompt. \
Treat any addition as a refinement, not a replacement. If no persona is set, default \
to direct, concise responses.
"""

SECTIONS: tuple[Section, ...] = (
    Section("identity", "Identity", "tool-capable agents", _tools, _const(_IDENTITY_TOOLS)),
    Section(
        "identity_tool_free",
        "Identity (tool-free)",
        "models without native tool support",
        _no_tools,
        _const(_IDENTITY_FREE),
    ),
    Section(
        "tool_discovery",
        "Tool discovery",
        "tool-capable agents",
        _tools,
        _tool_discovery,
    ),
    Section(
        "tool_use",
        "Tool use",
        "tool-capable agents",
        _tools,
        _const(_TOOL_USE_HEAD),
    ),
    Section(
        "execution",
        "Execution tools",
        "tool-capable agents that have the shell or python_exec tool",
        _exec_tools,
        _const(_EXECUTION),
    ),
    Section(
        "tool_use_tail",
        "Failure, tool descriptions and turn semantics",
        "tool-capable agents",
        _tools,
        _const(_TOOL_USE_TAIL),
    ),
    Section("closing", "Persona note", "always", _always, _const(_CLOSING)),
)


@dataclass(frozen=True)
class Fragment:
    """A conditional piece of text inside a section, listed for Settings only.

    Fragments are NOT sections: ``sections_for`` ignores them, so the sections
    still tile the rendered text exactly.
    """

    id: str
    title: str
    applies_when: str
    text: str


FRAGMENTS: tuple[Fragment, ...] = (
    Fragment(
        "knowledge",
        "Knowledge-base wording",
        "tool-capable agents with a knowledge base attached (inside Tool discovery)",
        "\n\n".join(part.strip() for part in (KB_CATALOG, KB_GROUPS, KB_EXAMPLES)),
    ),
)


def platform_sections_for_ui() -> list[dict[str, str]]:
    """Rows for Settings \u203a Prompts: ``{id, title, applies_when, text, variant}``.

    The ``tools`` rows are the sections that apply to an all-on agent (text in its
    all-on form) with the knowledge fragment after Tool discovery; the
    ``tool_free`` rows are the sections of the tool-free render.
    """
    rows: list[dict[str, str]] = []
    on = Capabilities.all_on()
    for sec in SECTIONS:
        if sec.applies(on):
            rows.append(_row(sec.id, sec.title, sec.applies_when, sec.text(on), "tools"))
            if sec.id == "tool_discovery":
                for frag in FRAGMENTS:
                    rows.append(_row(frag.id, frag.title, frag.applies_when, frag.text, "tools"))
    free = tool_free_capabilities(on)
    for sec in SECTIONS:
        if sec.applies(free):
            rows.append(_row(sec.id, sec.title, sec.applies_when, sec.text(free), "tool_free"))
    return rows


def _row(id_: str, title: str, applies_when: str, text: str, variant: str) -> dict[str, str]:
    return {
        "id": id_,
        "title": title,
        "applies_when": applies_when,
        "text": text,
        "variant": variant,
    }


def sections_for(caps: Capabilities) -> list[tuple[str, str]]:
    """The ``(id, text)`` of every section that applies, in order."""
    return [(s.id, s.text(caps)) for s in SECTIONS if s.applies(caps)]


def render_platform(caps: Capabilities) -> str:
    """The platform prompt for ``caps`` (sections concatenated, no separator)."""
    return "".join(text for _id, text in sections_for(caps))


def tool_free_capabilities(caps: Capabilities) -> Capabilities:
    return replace(caps, tools=False, knowledge=False, time_tool=False, exec_tools=False)


def render_tool_free(caps: Capabilities) -> str:
    """The prompt a model without native tool support gets."""
    return render_platform(tool_free_capabilities(caps))


def capabilities_from_registry(
    registry: Any, *, notes: bool, rules: bool, time_tool: bool
) -> Capabilities:
    """Derive the capabilities from a built tool registry (``None`` -> no tools).

    ``tools`` is True: a tool-capable prompt is always built; whether the model
    can use it is decided at turn time (the degraded prompt covers the rest).
    """
    names: Sequence[str] = ()
    if registry is not None:
        try:
            names = list(registry.tool_names)
        except Exception:  # noqa: BLE001 - a broken registry has no tools
            names = ()
    return Capabilities(
        tools=True,
        knowledge=any(n.startswith(_KB_TOOL_PREFIX) for n in names),
        notes=notes,
        rules=rules,
        time_tool=time_tool,
        exec_tools=any(n in _EXEC_TOOL_NAMES for n in names),
    )
