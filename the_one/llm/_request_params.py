from __future__ import annotations

import json
import os
from typing import Any

# M16 F11 L01 (A4 doc-gate + canonical resolvers): reasoning_effort,
# response_format, and stop are cross-provider request params (unlike the
# provider-local `resolve_extended_thinking` / `effective_num_ctx`), so their
# canonical resolvers live in this shared module rather than a
# provider-specific one (DD1/DD3 in flight.md; see the Leg 01 Wire-Format
# Premise in flight-log.md for the accepted-shape + per-model-default
# citations that justify each canonical mapping below).
#
# Precedence for all three resolvers, mirroring `resolve_extended_thinking`
# (`anthropic_provider.py`) and `effective_num_ctx` (`ollama_provider.py`):
# per-provider config → env → default `None`. The caller's `__init__` coerces
# the raw `config` value via the matching `_coerce_*` helper and passes an
# already-canonical `configured` value in (so an explicit, non-`None`
# `configured` always wins as-is, including an explicitly-empty coercion
# result if the caller chooses to pass one through). Each resolver itself
# coerces *only* the env read (env is always a raw string) via the same
# `_coerce_*` helper, at call time (not import time) — matching both
# in-repo precedents and keeping `_coerce_*` independently unit-testable.
#
# The canonical values produced here are provider-agnostic; mapping a
# canonical value to each provider's native request shape (Anthropic
# `output_config.effort` / `output_config.format` / `stop_sequences`; OpenAI
# `reasoning_effort` / `response_format` / `stop`; Ollama `/v1` and native
# equivalents) is done by each provider's own request-kwargs assembly in
# Legs 02-04 — this module only normalizes shape, it does not touch any
# provider request path.

_REASONING_EFFORT_ENV = "THE_ONE_REASONING_EFFORT"
_RESPONSE_FORMAT_ENV = "THE_ONE_RESPONSE_FORMAT"
_STOP_ENV = "THE_ONE_STOP"


def _coerce_effort(value: Any) -> str | None:
    """Coerce a free-form config/env value to a canonical effort string, or None.

    Accepts a non-empty ``str`` (stripped + lowercased). Rejects ``bool``
    explicitly (an ``int`` subclass, never a meaningful effort level) and
    everything else, collapsing to ``None`` so the resolver falls through to
    env/default. Deliberately does **not** hard-validate the allowed value
    set here — the accepted set differs per provider/model (see the Leg 01
    doc-gate), so per-provider validation belongs in the provider wiring legs
    (L02-L04); this canonical layer only normalizes shape.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        s = value.strip().lower()
        return s if s else None
    return None


def _coerce_response_format(value: Any) -> dict[str, Any] | None:
    """Coerce a free-form config/env value to a canonical response-format dict, or None.

    Canonical value space (decision, binds L02-L04 — see Leg 01 Wire-Format
    Premise): **both** variants are kept —

    - the string ``"json"``/``"json_object"`` (case-insensitive) coerces to
      canonical ``{"type": "json_object"}``;
    - a dict already shaped ``{"type": "json_object"}`` or
      ``{"type": "json_schema", "schema": {...}}`` passes through unchanged
      (only a shallow shape check — a wrong-shaped dict, e.g. missing
      ``type``, coerces to ``None``);
    - a JSON **string** (the env case) is decoded via ``json.loads`` and the
      decoded value is re-coerced through this same function (recursive,
      exactly one extra JSON-decode hop — the decoded value can only be a
      plain Python object at that point, so the recursion terminates);
    - anything else, or malformed JSON, coerces to ``None``, never raises.

    Anthropic's ``output_config.format`` has no bare-JSON-mode surface (only
    ``json_schema`` is accepted, per the Leg 01 doc-gate) — that gap is
    handled by the Anthropic wiring leg (a documented no-op/warning), not
    here; this resolver stays capable of producing ``json_object`` for the
    providers that do accept it (OpenAI, Ollama).
    """
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        low = s.lower()
        if low in ("json", "json_object"):
            return {"type": "json_object"}
        try:
            decoded = json.loads(s)
        except (ValueError, TypeError):
            return None
        if isinstance(decoded, str):
            # Avoid infinite recursion on a JSON string that decodes to
            # another string (e.g. '"json"' decoding to "json"); handle the
            # one extra hop inline instead of recursing indefinitely.
            low2 = decoded.strip().lower()
            return {"type": "json_object"} if low2 in ("json", "json_object") else None
        return _coerce_response_format(decoded)
    if isinstance(value, dict):
        fmt_type = value.get("type")
        if fmt_type == "json_object":
            return value
        if fmt_type == "json_schema" and "schema" in value:
            return value
        return None
    return None


def _coerce_stop(value: Any) -> list[str] | None:
    """Coerce a free-form config/env value to a canonical ``list[str]``, or None.

    Accepts a non-empty ``str`` (becomes a one-element list); a ``list``/
    ``tuple`` of non-empty ``str`` entries (non-``str``/empty entries are
    dropped; if nothing survives, coerces to ``None``); a JSON-array
    **string** (the env case), decoded via ``json.loads`` and re-coerced
    through this same function. Anything else, or malformed/wrong-shaped
    JSON (e.g. a JSON object rather than an array), coerces to ``None``,
    never raises.
    """
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            decoded = json.loads(s)
        except (ValueError, TypeError):
            # Not JSON at all: treat the whole string as one bare stop sequence.
            return [s]
        if isinstance(decoded, (list, dict)):
            # Only a JSON array/object changes shape (the env-array case, or
            # the wrong-shape-object case); a scalar decode (e.g. an env
            # value that happens to look like a bare number) is still just
            # the literal stop string, not a container to re-coerce.
            return _coerce_stop(decoded)
        return [s]
    if isinstance(value, dict):
        # A JSON object decodes fine but is never a valid stop shape.
        return None
    if isinstance(value, (list, tuple)):
        cleaned = [v for v in value if isinstance(v, str) and v]
        return cleaned if cleaned else None
    return None


def resolve_reasoning_effort(configured: str | None) -> str | None:
    """Precedence: per-provider config → env THE_ONE_REASONING_EFFORT → default None.

    ``configured`` is expected to already be canonical (the caller coerces
    the raw ``config`` value via ``_coerce_effort`` in its ``__init__``); a
    non-``None`` ``configured`` wins as-is. Only the env read is coerced
    here, at call time (not import time) so tests can monkeypatch
    ``os.environ`` freely.
    """
    if configured is not None:
        return configured
    env = _coerce_effort(os.environ.get(_REASONING_EFFORT_ENV))
    return env if env is not None else None


def resolve_response_format(configured: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Precedence: per-provider config → env THE_ONE_RESPONSE_FORMAT → default None.

    ``configured`` is expected to already be canonical (the caller coerces
    the raw ``config`` value via ``_coerce_response_format`` in its
    ``__init__``); a non-``None`` ``configured`` wins as-is. Only the env
    read (always a raw string, possibly JSON) is coerced here, at call time.
    """
    if configured is not None:
        return configured
    env = _coerce_response_format(os.environ.get(_RESPONSE_FORMAT_ENV))
    return env if env is not None else None


def resolve_stop(configured: list[str] | None = None) -> list[str] | None:
    """Precedence: per-provider config → env THE_ONE_STOP → default None.

    ``configured`` is expected to already be canonical (the caller coerces
    the raw ``config`` value via ``_coerce_stop`` in its ``__init__``); a
    non-``None`` ``configured`` wins as-is. Only the env read (always a raw
    string, possibly a JSON array) is coerced here, at call time.
    """
    if configured is not None:
        return configured
    env = _coerce_stop(os.environ.get(_STOP_ENV))
    return env if env is not None else None
