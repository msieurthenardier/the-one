"""Direct-tool-protocol renderer for non-tool-capable models (M16 F03 L08).

When a model's ``supports_tools()`` is ``False`` (e.g. ``gemma3:4b`` via
Ollama), the agent loop cannot offer it a native ``tools=`` array — Ollama
400s if it does. Instead the agent injects a **direct tool protocol** into
the system prompt: a pinned, deterministically-parseable call format plus a
compact catalog of the available tools. The model's resulting
``​```tool_code`` call is then recovered by the leg-01/07 recovery kernel
and dispatched normally.

This module is a pure renderer — it takes a list of tool schemas (the shape
``Tool.to_schema()`` produces: ``{"name", "description", "parameters"}``) and
returns the addendum string. No I/O, no network, deterministic.
"""

from __future__ import annotations

from typing import Any

# The format block comes FIRST (a single unmissable instruction) followed by
# the rules, then ONE worked example, then a tool-gating contrast pair, then the
# catalog — ordering tuned for a small model that skims. The fence tag
# (``tool_code``) and keyword-arg form are pinned to what the recovery kernel
# parses first-class. Two behavioral rules guard the small model's failure
# modes observed live (M16 F03 L08): a TOOL-GATING clause (answer ordinary
# knowledge questions directly, do NOT route them through a tool — fixes CP5
# over-routing) and a POST-TOOL STOP clause (after a tool result, write a final
# answer rather than re-calling the same tool — fixes CP4 looping).
_PROTOCOL_HEADER = """\
You do not have native tool-calling. To call a tool, output EXACTLY one fenced \
block and nothing else in the message — no prose before or after:
```tool_code
tool_name(arg1="value1", arg2="value2")
```
Rules:
- Use KEYWORD arguments matching the parameter names shown in the catalog below.
- Use DOUBLE-QUOTED string values (do not put unescaped double-quotes inside a value).
- Call ONE tool per message — you will get its result and may call another.
- Emit ONLY the fenced block when calling a tool. No prose before or after it.
- Only use a tool when the task genuinely requires an external action — running a \
command, reading or writing a file, fetching data, etc. For questions you can answer \
from your own knowledge (definitions, explanations, general facts), answer directly in \
natural language and do NOT call any tool.
- After you receive a tool result, do NOT call the same tool again for the same \
purpose. Read the result and write a final, natural-language answer to the user that \
incorporates it. Only call another tool if the task genuinely needs a further, \
different action.

Example — to run a shell command:
```tool_code
shell(command="echo hello")
```

Contrast — when to use a tool and when not to:
- Ordinary question (answer directly, no tool):
  User: What is a haiku?
  You: A haiku is a three-line Japanese poem with a 5-7-5 syllable pattern.
- Action request (call a tool):
  User: How many files are in this directory?
  ```tool_code
  shell(command="ls -1 | wc -l")
  ```"""


def _param_names(schema: dict[str, Any]) -> list[str]:
    """Extract the parameter names for a tool schema, required first.

    Reads ``parameters.properties`` (declaration order) and orders the
    required names ahead of the optional ones while preserving each group's
    declaration order. Tolerant of missing/empty ``parameters``.
    """
    params = schema.get("parameters") or {}
    properties = params.get("properties") or {}
    required = params.get("required") or []
    required_set = set(required)
    req = [name for name in properties if name in required_set]
    opt = [name for name in properties if name not in required_set]
    return req + opt


def build_degraded_tool_prompt(tool_schemas: list[dict]) -> str:
    """Render the direct-tool-protocol addendum from a list of tool schemas.

    ``tool_schemas`` is the ``Tool.to_schema()`` shape
    (``{"name", "description", "parameters"}``). The output pins the
    ``​```tool_code`` call format (with one worked example) and then lists
    each tool as ``name(param, param): description``.

    Pure and deterministic; no I/O. Compact by design — a small model has a
    short context, so descriptions are emitted on a single line and the format
    spec is stated once.
    """
    lines = [_PROTOCOL_HEADER, "", "Available tools:"]
    if not tool_schemas:
        # Edge case: no callable tools. State it plainly rather than emitting
        # an empty bullet list so the model isn't left guessing.
        lines.append("- (none available — respond with text only)")
        return "\n".join(lines)

    for schema in tool_schemas:
        name = schema.get("name", "")
        description = (schema.get("description") or "").strip().replace("\n", " ")
        names = _param_names(schema)
        sig = f"{name}({', '.join(names)})"
        if description:
            lines.append(f"- {sig}: {description}")
        else:
            lines.append(f"- {sig}")
    return "\n".join(lines)
