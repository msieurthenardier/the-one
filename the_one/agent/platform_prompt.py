"""The platform prompt: the text the platform itself puts before every agent.

Built from ordered :class:`Section` objects so each part is nameable (the evals
measure them by section; Settings › Prompts will list them). Sections are
concatenated with NO separator inserted by the renderer: each section's text
carries its own leading whitespace, which is what lets the execution bullet sit
mid-way through the "Tool use:" block.

Two variants exist: the tool-capable prompt (``caps.tools``) and the tool-free
prompt a model without native tool support receives (M16 F03 L08C, #105: no
catalog, no ``continue`` semantics, so the model converses naturally).

The prompt is sectioned and capability-conditioned: ``caps.tools`` selects the
tool-capable or tool-free variant, and the knowledge line and the execution
section appear only when the agent has the matching tools (see
:func:`sections_for`). The remaining capability fields do not change this text.
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
    # Sortie 11 DD3: every enabled tool schema is offered up front, so the discovery
    # section says so instead of describing `search_tools` discovery.
    tools_preloaded: bool = False
    # Mission 35 DD12: the agent's Rich visuals switch; the chart-writing instructions.
    visuals: bool = True

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


def _always(caps: Capabilities) -> bool:
    return True


def _tools(caps: Capabilities) -> bool:
    return caps.tools


def _no_tools(caps: Capabilities) -> bool:
    return not caps.tools


def _exec_tools(caps: Capabilities) -> bool:
    return caps.tools and caps.exec_tools


_IDENTITY_TOOLS = (
    "You are an AI agent. Use your tools to do what you're asked, and reply directly "
    "and concisely.\n"
)

# Tool discovery. The knowledge line is appended inside the section
# only when the agent has a knowledge base attached; both forms are pinned verbatim.
NO_KB_TOOL_DISCOVERY = (
    "\nTools:\n"
    "- You start with `search_tools` and `continue`. Find any other tool with "
    '`search_tools` (for example "read a file" or "http request"); tools you find '
    "stay available for the rest of the conversation.\n"
)
KB_LINE = (
    "- Knowledge bases are attached: list them with `search_tools` (empty query) and "
    "search them before answering from memory on topics they cover.\n"
)


# The wording for an agent whose whole toolset is offered up front (sortie 11 DD3,
# operator-approved copy B). Pinned verbatim by tests.
PRELOADED_TOOL_DISCOVERY = (
    "\nTools:\n"
    "- All your tools are available now: call them directly (`search_tools` only lists "
    "them again).\n"
)
PRELOADED_KB_LINE = (
    "- Knowledge bases are attached: search them before answering from memory on topics "
    "they cover.\n"
)


def _tool_discovery(caps: Capabilities) -> str:
    if caps.tools_preloaded:
        return PRELOADED_TOOL_DISCOVERY + (PRELOADED_KB_LINE if caps.knowledge else "")
    return NO_KB_TOOL_DISCOVERY + (KB_LINE if caps.knowledge else "")


_TOOL_USE_HEAD = (
    "- Take actions rather than describing them. If a tool fails, try another way "
    "and say what you changed."
)

_EXECUTION = """
- Execution tools default to an isolated box with no access to the user's files or \
network; request host access only when the task concretely needs the user's real \
files or network."""

_TOOL_USE_TAIL = (
    "\n- To keep working in another step, call `continue`; otherwise your text reply "
    "ends the turn.\n"
)

_FORMATTING = "\nWrite replies in Markdown, and write links as [text](url).\n"

_VISUALS = (
    "\nTo show a chart, reply with a code block whose language is `chart` and whose body "
    "is one JSON object, `type` first:\n"
    "```chart\n"
    '{"type": "bar", "x": {"values": ["Q1", "Q2"]}, '
    '"series": [{"name": "Sales", "values": [12, 19]}]}\n'
    "```\n"
    "Data always goes in `series`; `x` and `y` only describe the axes. "
    "Types: bar, line, area, scatter, pie, sparkline. "
    'A pie takes slice names from `"x": {"values": [...]}` and has one series. '
    "Optional: `title`, axis `label` and "
    '`unit`, `"stacked": true`. Two axes: add `"y2"` shaped like `"y"` and set a series '
    '`"axis": "right"`; a series `"type": "line"` mixes a line into bars; reference lines: '
    '`"annotations": [{"axis": "y", "value": 150, "label": "Target"}]`; log scale: '
    '`"scale": "log"` on `y` (`x` for scatter). Chart only when it makes numbers clearer.\n'
    "To show something moving or interactive, reply with a code block whose language is "
    "`widget` and whose body is one self-contained HTML snippet with inline `<style>` and "
    "`<script>`:\n"
    "```widget\n"
    '<canvas id="c"></canvas>\n'
    "<script>\n"
    'const g = c.getContext("2d"), css = getComputedStyle(document.documentElement);\n'
    "function frame(t) {\n"
    '  g.fillStyle = css.getPropertyValue("--accent"); /* draw */\n'
    "  requestAnimationFrame(frame);\n"
    "}\n"
    "requestAnimationFrame(frame);\n"
    "</script>\n"
    "```\n"
    "Colours: `var(--surface)`, `var(--fg)`, `var(--accent)`, `var(--chart-1)` to "
    "`var(--chart-8)` in CSS; on a canvas, read them with `getPropertyValue` as above. "
    "It runs with no network: no URLs, CDNs or remote images. Use a widget for animation "
    "or interaction, a chart for plain data.\n"
)

_IDENTITY_FREE = "You are an AI assistant. Reply directly and concisely.\n"

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
        "Turn semantics",
        "tool-capable agents",
        _tools,
        _const(_TOOL_USE_TAIL),
    ),
    Section("formatting", "Formatting", "always", _always, _const(_FORMATTING)),
    Section(
        "visuals",
        "Rich visuals",
        "agents with Rich visuals on",
        lambda c: c.visuals,
        _const(_VISUALS),
    ),
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
        KB_LINE.strip(),
    ),
)

# Settings-only rows for the preloaded wording (sortie 11 DD3). Kept out of ``FRAGMENTS``
# so that tuple stays the knowledge line alone; ``tool_discovery_preloaded`` is built from
# ``_tool_discovery`` in :func:`platform_sections_for_ui`.
PRELOADED_FRAGMENTS: tuple[Fragment, ...] = (
    Fragment(
        "knowledge_preloaded",
        "Knowledge-base wording (tools preloaded)",
        "tool-capable agents whose tools fit the exposure budget, with a knowledge base "
        "attached (inside Tool discovery)",
        PRELOADED_KB_LINE.strip(),
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
                rows.append(
                    _row(
                        "tool_discovery_preloaded",
                        "Tool discovery (tools preloaded)",
                        "tool-capable agents whose tools fit the exposure budget",
                        _tool_discovery(replace(on, tools_preloaded=True)),
                        "tools",
                    )
                )
                for frag in PRELOADED_FRAGMENTS:
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
    return replace(
        caps,
        tools=False,
        knowledge=False,
        time_tool=False,
        exec_tools=False,
        tools_preloaded=False,
    )


def render_tool_free(caps: Capabilities) -> str:
    """The prompt a model without native tool support gets."""
    return render_platform(tool_free_capabilities(caps))


def capabilities_from_registry(
    registry: Any,
    *,
    notes: bool,
    rules: bool,
    time_tool: bool,
    tools_preloaded: bool = False,
    visuals: bool = True,
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
        tools_preloaded=tools_preloaded,
        visuals=visuals,
    )
