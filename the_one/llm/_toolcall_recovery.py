"""Pure text-form tool-call recovery kernel for loose/open-model output.

M16 F03 L01 (#105): open/local models (e.g. gemma3:4b via Ollama) often
emit a tool call as loose text — a fenced Python-call block, a Hermes
<tool_call> tag, or a bare JSON object — instead of a structured
tool_calls array. This kernel recovers those into plain dicts that the
Ollama adapter (M16 F03 L02) maps to ToolCall.

Import discipline: stdlib only (ast, json, re). This is a true leaf —
it imports nothing from the_one, so it is unit-testable with no provider
or network. NEVER uses builtin eval; ast.parse + ast.literal_eval only.

Dispatch (most-specific recognizer first; FIRST non-empty list wins, and
its full list is returned — no recovery from later recognizers):

  1. Hermes ``<tool_call>…</tool_call>`` tags (all tags, document order).
  2. Fenced `````tool`` / untagged / `````python`` blocks
     whose body is a single Python call.
  3. Whole-content bare-JSON object of tool-call shape (tightest gate).

This makes *within-format* multi-call work (a recognizer returns all its
own matches) while keeping *cross-format* mixed multi-call deliberately
out of scope — matching the captured reality that a model emits one
format at a time.

Every returned element is exactly ``{"name": str, "arguments": dict}``.
``recover_tool_calls`` is total over ``str``: malformed input never
raises — a bad match contributes nothing rather than propagating.

``__positional_args__`` is a reserved sentinel key (see
``_parse_python_call``): real tool schemas are assumed never to define a
parameter of that name; leg 02's dispatcher treats it specially.
"""

from __future__ import annotations

import ast
import json
import logging
import re

logger = logging.getLogger(__name__)

# Reserved sentinel key under which recovered positional args are carried
# so they are never silently dropped (leg 02's dispatcher special-cases it).
POSITIONAL_ARGS_KEY = "__positional_args__"

# Hermes tag body, matched up to the CLOSING tag (re.DOTALL) — NOT up to the
# first ``}``. A non-greedy ``(\{.*?\})`` would truncate a payload whose
# ``arguments`` contains a nested object at the first inner ``}``.
_HERMES_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)

# Fenced code block: optional language/info tag on the open fence, body, close.
_FENCE_RE = re.compile(
    r"```[ \t]*([^\n`]*)\n(.*?)```",
    re.DOTALL,
)

# Fence info-strings whose body we attempt to parse as a Python call.
# ``tool_code`` is Gemma/Gemini's documented fenced-tool-call convention
# (real gemma3:4b emits ` ```tool_code `); the others are the original set.
_FENCE_TAGS_TO_PARSE = {"", "tool", "tool_code", "python", "py"}


def recover_tool_calls(content: str) -> list[dict]:
    """Recover text-form tool calls from loose model output.

    Returns a list of ``{"name": str, "arguments": dict}`` dicts, or
    ``[]`` when no high-precision marker is present. Total over ``str``:
    never raises.

    Thin wrapper over ``recover_and_strip`` that drops the stripped-content
    half — preserved for callers that only need the recovered calls.
    """
    _stripped, calls = recover_and_strip(content)
    return calls


def recover_and_strip(content: str) -> tuple[str, list[dict]]:
    """Recover text-form calls AND strip the recognized block(s) in one pass.

    Returns ``(stripped_content, calls)`` where ``calls`` is the same list
    ``recover_tool_calls`` returns and ``stripped_content`` is ``content``
    with the spans the winning recognizer matched removed (DD4). When
    nothing is recovered, returns ``(content, [])`` unchanged.

    The kernel owns both the dispatch-winner selection and the spans, so the
    adapter never re-implements any marker knowledge. Total over ``str``:
    never raises. If stripping leaves only whitespace, the stripped content
    is ``""``.
    """
    if not content or not content.strip():
        return content, []

    for recognizer in (_recover_hermes, _recover_fences, _recover_bare_json):
        try:
            calls, spans = recognizer(content)
        except Exception:  # pragma: no cover - defensive; helpers self-guard
            calls, spans = [], []
        if calls:
            stripped = _strip_spans(content, spans)
            return stripped, calls
    return content, []


def _strip_spans(content: str, spans: list[tuple[int, int]]) -> str:
    """Remove ``spans`` (start, end half-open indices) from ``content``.

    Spans are removed in document order. If the remainder is only
    whitespace, returns ``""`` (DD4: whole-content recovery yields empty
    content). Otherwise the surrounding prose is preserved verbatim.
    """
    if not spans:
        return content
    out: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        out.append(content[cursor:start])
        cursor = end
    out.append(content[cursor:])
    stripped = "".join(out)
    return "" if not stripped.strip() else stripped


# ---------------------------------------------------------------------------
# Recognizer 1: Hermes <tool_call>…</tool_call> tags
# ---------------------------------------------------------------------------


def _recover_hermes(content: str) -> tuple[list[dict], list[tuple[int, int]]]:
    """Recover all ``<tool_call>…</tool_call>`` tags in document order.

    Each tag body is parsed as JSON; tags whose body is invalid JSON or
    lacks a ``name`` are skipped (no KeyError, no raise). Returns the
    recovered calls and the ``(start, end)`` spans of the full tags that
    produced a call (for stripping).
    """
    calls: list[dict] = []
    spans: list[tuple[int, int]] = []
    for m in _HERMES_RE.finditer(content):
        try:
            obj = json.loads(m.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            continue
        call = _normalize_json_call(obj)
        if call is not None:
            calls.append(call)
            spans.append((m.start(), m.end()))
    return calls, spans


# ---------------------------------------------------------------------------
# Recognizer 2: fenced Python-call blocks (the gemma path, first-class)
# ---------------------------------------------------------------------------


def _recover_fences(content: str) -> tuple[list[dict], list[tuple[int, int]]]:
    """Recover fenced blocks whose body is a single bare Python call.

    Accepts `````tool`` (primary), untagged ``````` and
    `````python`` fences. Each body is parsed with
    ``_parse_python_call``; bodies that aren't a single call contribute
    nothing. Returns the recovered calls and the ``(start, end)`` spans of
    the full fenced blocks that produced a call (for stripping).
    """
    calls: list[dict] = []
    spans: list[tuple[int, int]] = []
    for m in _FENCE_RE.finditer(content):
        tag = m.group(1).strip().lower()
        if tag not in _FENCE_TAGS_TO_PARSE:
            continue
        call = _parse_python_call(m.group(2))
        if call is not None:
            calls.append(call)
            spans.append((m.start(), m.end()))
    return calls, spans


def _parse_python_call(src: str) -> dict | None:
    """Parse a single Python-call expression into a tool-call dict.

    Returns ``{"name": str, "arguments": dict}`` or ``None`` when the
    source is not a single call, has a non-name/attribute callee, or
    carries any non-literal argument (we never partially recover).

    Positional args are carried under ``arguments[POSITIONAL_ARGS_KEY]``
    (never silently dropped) and a WARN is logged; keyword and positional
    args coexist in the same dict.
    """
    try:
        tree = ast.parse(src.strip(), mode="eval")
    except (SyntaxError, ValueError):
        return None

    node = tree.body
    if not isinstance(node, ast.Call):
        return None

    name = _callee_name(node.func)
    if name is None:
        return None

    arguments: dict = {}
    try:
        for kw in node.keywords:
            if kw.arg is None:  # **kwargs splat — not a literal mapping
                return None
            arguments[kw.arg] = ast.literal_eval(kw.value)
        positional = [ast.literal_eval(a) for a in node.args]
    except (ValueError, SyntaxError, TypeError):
        return None

    if positional:
        arguments[POSITIONAL_ARGS_KEY] = positional
        logger.warning(
            "recovered positional args for %s; built-in/MCP tools expect named args",
            name,
        )

    return {"name": name, "arguments": arguments}


def _callee_name(func: ast.expr) -> str | None:
    """Return the function name: ``Name.id`` or a dotted ``Attribute`` path.

    Returns ``None`` for any other callee form (e.g. a subscript or call).
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = []
        cur: ast.expr = func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if not isinstance(cur, ast.Name):
            return None
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


# ---------------------------------------------------------------------------
# Recognizer 3: whole-content bare-JSON object (tightest gate)
# ---------------------------------------------------------------------------


def _recover_bare_json(content: str) -> tuple[list[dict], list[tuple[int, int]]]:
    """Recover a tool-call-shaped JSON object that IS the whole content.

    Only fires when ``content.strip()`` starts with ``{`` and parses as a
    dict of accepted tool-call shape. Never fires mid-prose (DD2
    whole-content gate). Returns ``([], [])`` for anything else. The strip
    span is the whole content, so the stripped remainder is ``""``.
    """
    stripped = content.strip()
    if not stripped.startswith("{"):
        return [], []
    try:
        obj = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return [], []
    if not isinstance(obj, dict):
        return [], []
    call = _normalize_json_call(obj)
    if call is None:
        return [], []
    return [call], [(0, len(content))]


# ---------------------------------------------------------------------------
# Shared JSON-shape normalization (Hermes + bare-JSON)
# ---------------------------------------------------------------------------


def _normalize_json_call(obj: object) -> dict | None:
    """Normalize a parsed JSON object to ``{"name": str, "arguments": dict}``.

    Accepts these shapes:
      - ``{"name": str, "arguments": dict}`` (arguments optional → ``{}``)
      - ``{"type": "function", "function": {"name", "arguments"}}`` (unwrap)
      - ``{"tool"|"function": str, "arguments"|"parameters": dict}``
    Returns ``None`` for anything else.
    """
    if not isinstance(obj, dict):
        return None

    # OpenAI-style function wrapper: {"type": "function", "function": {...}}
    inner = obj.get("function")
    if isinstance(inner, dict):
        return _normalize_json_call(inner)

    # Name under any of the accepted keys.
    name = obj.get("name")
    if not isinstance(name, str):
        candidate = obj.get("tool")
        name = candidate if isinstance(candidate, str) else None
    if not isinstance(name, str) or not name:
        return None

    # Arguments under "arguments" or "parameters"; default to {}.
    args = obj.get("arguments")
    if not isinstance(args, dict):
        params = obj.get("parameters")
        args = params if isinstance(params, dict) else {}

    return {"name": name, "arguments": args}
