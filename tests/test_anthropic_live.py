"""Live-gated correctness tests for the Anthropic tool ``input_schema``
sanitizer (M16 F02 #122).

These tests confirm that our *model* of Anthropic's #122 rule is correct,
not just internally consistent: the **real** Anthropic Messages API
**accepts** the sanitizer's output for the ``press_key`` schema and still
**400s** on the un-sanitized original — and they pin leg 01's provisional
array-``type`` collapse rule against real Anthropic behavior.

Marker: ``@pytest.mark.live`` — deselected from the default ``pytest`` run
(``pyproject.toml`` ``addopts = "-m 'not live and ...'"``). Each test
additionally self-skips when ``ANTHROPIC_API_KEY`` is unset, so the module
is safe in keyless CI.

Cost: these make REAL Anthropic API calls. They are kept trivially cheap —
``max_tokens=16`` and one-line prompts. The #122 rejection is a
request-validation error that fires *before* model inference, so the cheap
``claude-haiku-4-5-20251001`` default is a valid proxy for any Anthropic
model the operator routes to in production. No assertions are made on model
output, only on request acceptance/rejection.

Model override: ``LIVE_ANTHROPIC_MODEL`` (default
``claude-haiku-4-5-20251001``), mirroring
``tests/test_input_tokens_cross_provider_live.py``.

Operator invocation:

    set -a && . ./.env && set +a && \\
        .venv/bin/pytest -m live tests/test_anthropic_live.py -v
"""

from __future__ import annotations

import os
import re

import anthropic
import pytest

from the_one.llm._schema_sanitize import sanitize_tool_schema
from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.base import Message, Role

pytestmark = pytest.mark.live

_MODEL = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
_skip = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)

# The real-world #122 trigger: goldfinch's ``press_key`` tool input_schema,
# inlined verbatim (top-level ``anyOf`` alongside a top-level ``type``).
# Matches ``tests/test_schema_sanitize.py``'s ``PRESS_KEY_INPUT_SCHEMA`` so the
# two stay in lockstep without a cross-file import.
PRESS_KEY_RAW = {
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


@_skip
async def test_real_anthropic_accepts_sanitized_press_key_through_provider() -> None:
    """End-to-end through the provider: leg 02's in-adapter sanitize makes the
    formerly-400ing ``press_key`` tool work against the live API.

    The adapter sanitizes the schema internally before send (leg 02); if the
    real API rejected the sanitized schema the call would raise. So a clean
    return IS the load-bearing assertion — the sanity check on the returned
    ``Message`` only guards against a future SDK change returning something
    falsy-but-non-raising.
    """
    provider = AnthropicProvider(model=_MODEL)
    try:
        tool = {
            "name": "press_key",
            "description": "Press a keyboard key in the target tab.",
            "parameters": PRESS_KEY_RAW,
        }
        result = await provider.complete(
            messages=[Message.user("Say hi.")],
            tools=[tool],
            max_tokens=16,
        )
        assert isinstance(result, Message)
        # Cheap, non-vacuous sanity: a real assistant turn came back.
        assert result.role == Role.ASSISTANT or result.usage is not None
    finally:
        await provider.aclose()


@_skip
async def test_real_anthropic_rejects_unsanitized_press_key_direct() -> None:
    """A direct SDK call (bypassing the adapter's sanitize) with the raw
    top-level-``anyOf`` schema must 400 — proving the acceptance test above is
    meaningful, not vacuous.

    Assertion robustness: the exact #122 wording was only observed via the
    OpenRouter->Bedrock relay, never against the first-party API. So we bind on
    ``BadRequestError`` AND ``"anyOf"`` AND a tolerant ``top[- ]level`` match
    rather than the literal ``"top level"`` substring. The full message is
    printed (flush) so the exact first-party wording is captured in ``-v``
    output and can be copied into the flight log.
    """
    provider = AnthropicProvider(model=_MODEL)
    try:
        native_tool = {
            "name": "press_key",
            "description": "Press a keyboard key in the target tab.",
            "input_schema": PRESS_KEY_RAW,
        }
        with pytest.raises(anthropic.BadRequestError) as excinfo:
            await provider.client.messages.create(
                model=_MODEL,
                max_tokens=16,
                messages=[{"role": "user", "content": "Say hi."}],
                tools=[native_tool],
            )
        msg = str(excinfo.value)
        print(f"\n[#122 first-party rejection wording] {msg}", flush=True)
        assert excinfo.value.status_code == 400
        assert "anyOf" in msg, f"expected 'anyOf' in rejection message, got: {msg!r}"
        assert re.search(r"top[- ]level", msg, re.I), (
            f"expected a 'top-level'/'top level' phrase in rejection message, got: {msg!r}"
        )
    finally:
        await provider.aclose()


@_skip
async def test_array_type_pin_sanitized_object_accepted_direct() -> None:
    """Pin leg 01's provisional array-``type`` collapse rule against real
    Anthropic behavior.

    Send, via a direct SDK call, a tool whose ``input_schema`` has top-level
    ``type: ["object", "null"]``; record whether Anthropic accepts or rejects
    it. Then send the leg-01-sanitized form (scalar ``type: "object"``) and
    assert it is ACCEPTED — that is the binding assertion.

    Divert semantics: if the raw-array call is accepted, fine (our collapse is
    still valid — scalar object is a subset). If the SANITIZED form is
    rejected, STOP — that means leg 01's collapse rule is wrong (the test will
    fail on the binding assert, surfacing the divert).
    """
    provider = AnthropicProvider(model=_MODEL)
    try:
        raw_array_schema = {
            "type": ["object", "null"],
            "properties": {"x": {"type": "string"}},
        }

        # Record the raw-array outcome (informational; not the binding assert).
        raw_tool = {
            "name": "array_type_probe",
            "description": "Probe whether Anthropic accepts a top-level array type.",
            "input_schema": raw_array_schema,
        }
        try:
            await provider.client.messages.create(
                model=_MODEL,
                max_tokens=16,
                messages=[{"role": "user", "content": "Say hi."}],
                tools=[raw_tool],
            )
            raw_outcome = "accepted"
        except anthropic.BadRequestError as exc:
            raw_outcome = f"rejected: {exc}"
        print(
            f"\n[array-type pin] raw top-level type=['object','null'] -> {raw_outcome}",
            flush=True,
        )

        # Binding assertion: the leg-01-sanitized (scalar ``type: 'object'``)
        # form is accepted.
        sanitized_schema = sanitize_tool_schema(raw_array_schema)
        assert sanitized_schema["type"] == "object", (
            f"sanitizer did not collapse the array type to scalar 'object': {sanitized_schema!r}"
        )
        sanitized_tool = {
            "name": "array_type_probe",
            "description": "Probe whether Anthropic accepts the sanitized scalar type.",
            "input_schema": sanitized_schema,
        }
        result = await provider.client.messages.create(
            model=_MODEL,
            max_tokens=16,
            messages=[{"role": "user", "content": "Say hi."}],
            tools=[sanitized_tool],
        )
        # A clean return is the load-bearing assertion (no raise == accepted).
        assert result is not None
        print("\n[array-type pin] sanitized scalar type='object' -> accepted", flush=True)
    finally:
        await provider.aclose()
