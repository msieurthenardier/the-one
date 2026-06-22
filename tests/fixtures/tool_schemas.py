"""Shared test fixtures for tool-schema / Anthropic-error tests (M16 F04 L01).

DD6 of the cross-provider conformance suite: with four consumers, the
``press_key`` tool ``input_schema`` and the ``BadRequestError`` builder are
defined here once rather than copied per file. Importers use the absolute
package form (matching ``--import-mode=importlib`` in ``pyproject.toml`` and the
existing ``tests.fixtures.mcp.*`` imports)::

    from tests.fixtures.tool_schemas import PRESS_KEY_INPUT_SCHEMA, make_bad_request

The module imports only ``anthropic`` + ``httpx`` (already test deps) and
stdlib — no ``the_one.*`` import, so it adds no production coupling.
"""

from __future__ import annotations

import anthropic
import httpx

# The real-world #122 trigger: goldfinch's ``press_key`` tool input_schema
# (top-level ``anyOf`` alongside a top-level ``type``), inlined verbatim
# (source: goldfinch ``src/main/automation/mcp-tools.js``).
PRESS_KEY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "wcId": {"type": "integer", "description": "webContents id of the target tab"},
        "name": {"type": "string", "description": "friendly key name (preferred) ..."},
        "key": {"type": "string", "description": "accepted alias for `name` ..."},
        "modifiers": {
            "type": "array",
            "items": {"type": "string", "enum": ["control", "shift", "alt", "meta"]},
            "description": "optional modifier keys held during the press ...",
        },
    },
    "required": ["wcId"],
    "anyOf": [{"required": ["name"]}, {"required": ["key"]}],
}

# A genuinely-unsanitizable top-level combinator: the ``anyOf`` branch is a
# bare scalar (``{"type": "string"}``), not an object fragment, so it cannot be
# flattened into the parent object — ``sanitize_tool_schema`` raises
# ``UnsanitizableToolSchema``. The representative #122 "can't flatten" case,
# used to pin the forward-with-WARN (OpenRouter ``anthropic/*``) vs.
# drop-and-proceed (Anthropic-direct) route asymmetry.
UNSANITIZABLE_ANYOF_SCHEMA = {"anyOf": [{"type": "string"}]}


def make_bad_request(msg: str) -> anthropic.BadRequestError:
    """Construct a BadRequestError (response/body are required kwonly).

    Only the message string is load-bearing — the provider error path reads
    str(err) only, never .body or .response.headers.
    """
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.BadRequestError(msg, response=httpx.Response(400, request=req), body=None)
