"""Schema-guided scalar coercion for MCP tool arguments (squawk 0052).

Some models send integer / number / boolean fields as strings (``{"wcId": "7"}``).
``coerce_arguments`` converts such a string to the declared scalar, immediately
before ``jsonschema`` validation in ``MCPClient.call_tool``. Pure stdlib.

Contract (deliberately conservative; a value the schema already accepts is never
changed):

* One direction only: ``str`` -> ``int`` / ``float`` / ``bool``. Non-string values
  are never touched.
* A string is converted only when the declared ``type`` is unambiguous and
  excludes ``"string"`` (``"integer"``, ``"number"``, ``"boolean"``, or a list such
  as ``["integer", "null"]`` without ``"string"``). A schema using ``anyOf`` /
  ``oneOf`` / ``allOf`` / ``$ref`` / ``enum`` / ``const`` (or with no ``type``) is
  left as is; combinators are not resolved.
* integer: base-10 integer string, optional leading ``-``, surrounding whitespace
  allowed. No ``+``, no ``"7.0"``, ``"1e3"``, ``"0x10"`` or underscores.
* number: integer or decimal / exponent literal (same ``-`` / whitespace / no
  underscore rules). An integer literal yields ``int``, anything else ``float``
  (both satisfy jsonschema ``number``). ``nan`` / ``inf`` and overflow are rejected.
* boolean: exactly ``true`` / ``false``, case-insensitive, whitespace trimmed.
* Recursion only where the schema describes structure: ``properties`` of an object
  value and a single-schema ``items`` of an array value. ``additionalProperties``,
  ``patternProperties`` and tuple-form ``items`` are not followed.
* The input is never mutated; a new structure is returned (unchanged branches may
  be shared with the input).
"""

from __future__ import annotations

import math
import re
from typing import Any

_INT_RE = re.compile(r"-?[0-9]+", re.ASCII)
_NUM_RE = re.compile(r"-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)

_BLOCKING_KEYS = ("anyOf", "oneOf", "allOf", "$ref", "enum", "const", "not", "if")


def _declared_types(schema: dict[str, Any]) -> set[str]:
    t = schema.get("type")
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return {x for x in t if isinstance(x, str)}
    return set()


def _coerce_string(value: str, types: set[str]) -> Any:
    s = value.strip()
    if "integer" in types and _INT_RE.fullmatch(s):
        return int(s)
    if "number" in types and _NUM_RE.fullmatch(s):
        if _INT_RE.fullmatch(s):
            return int(s)
        f = float(s)
        if math.isfinite(f):
            return f
    if "boolean" in types:
        low = s.lower()
        if low == "true":
            return True
        if low == "false":
            return False
    return value


def _coerce(value: Any, schema: Any) -> Any:
    if not isinstance(schema, dict) or any(k in schema for k in _BLOCKING_KEYS):
        return value
    types = _declared_types(schema)
    if isinstance(value, str):
        if "string" in types or not types & {"integer", "number", "boolean"}:
            return value
        return _coerce_string(value, types)
    if isinstance(value, dict):
        props = schema.get("properties")
        if isinstance(props, dict):
            return {k: _coerce(v, props[k]) if k in props else v for k, v in value.items()}
        return value
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            return [_coerce(v, items) for v in value]
    return value


def coerce_arguments(arguments: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``arguments`` with string scalars coerced per ``schema``."""
    result = _coerce(arguments, schema)
    return result if isinstance(result, dict) else arguments
