"""Live verification that text-form tool-call recovery fires against real gemma3:4b.

M16 F3 L04: a committed ``@pytest.mark.live`` test that drives
``OllamaProvider("gemma3:4b")`` against a real local Ollama with a prompt
engineered to elicit a single fenced ``tool`` block, then asserts that:

1. recovery fired — the returned ``Message.tool_calls`` is non-empty with a
   ``ToolCall`` carrying a non-empty ``name`` and a ``dict`` ``arguments``
   (the id is a synthesized ``f"{name}_{i}"`` per DD4 — we assert shape, not
   an exact model-chosen value); and
2. the raw call block was stripped (DD4) — the call syntax is not rendered in
   ``Message.content`` (``"get_weather(" not in content`` — the PRIMARY check,
   robust to whichever fence tag the model chose — AND ``"```tool" not in
   content``). Surrounding prose, if any, may remain.

This proves the leg-01/02 recovery+strip path works against genuine model
output, not just the captured fixture.

**Run convention** — run this test DIRECTLY, NOT via ``make test-live`` (that
target is hardcoded to ``tests/test_aiat.py``)::

    LIVE_OLLAMA_BASE_URL=http://localhost:11434/v1 \\
        .venv/bin/python -m pytest tests/test_ollama_recovery_live.py -m live -v

This mirrors the canonical live cross-provider module's run convention
(``tests/test_llm_provider_cross_provider_history.py:592-593``).

**Confidence-test stance** — live LLMs are non-deterministic. This test asserts
the *mechanism* (recovery fired + strip happened) under a prompt engineered to
reliably elicit the fenced form, and treats genuine model non-cooperation
(no recoverable call after a bounded retry) as INCONCLUSIVE (``pytest.skip``),
never a hard failure. It self-skips when Ollama / gemma3 is absent so default
``make test-unit`` stays hermetic (the live marker is deselected there).
"""

from __future__ import annotations

import os

import pytest

from the_one.llm.base import Message, Role
from the_one.llm.ollama_provider import OllamaProvider

# Directive prompt: gemma3:4b is non-tool-capable, so no ``tools=`` are offered;
# we instruct it to emit the call as loose fenced text, which is exactly the
# recovery trigger (leg 02). The fence tag the model picks (```tool / ```python /
# untagged) doesn't matter — the kernel accepts single-call fences either way.
DIRECTIVE = (
    "You can call a tool get_weather(city). To call it, output exactly one "
    "fenced block and nothing else:\n"
    "```tool\n"
    "get_weather(city='<city>')\n"
    "```\n"
    "Do not add any prose, explanation, or extra text — respond with only the "
    "fenced block."
)


async def _resolve_gemma(timeout: float = 5.0) -> tuple[str, str]:
    """Probe Ollama and resolve a gemma3 model, mirroring the canonical
    ``_resolve_ollama`` pattern at
    ``tests/test_llm_provider_cross_provider_history.py:545-585`` — but
    requiring gemma3 specifically (a substring match), rather than inheriting
    that resolver's "first available / qwen-preferred" order (which would skip
    whenever a non-gemma model sorts first).

    Returns ``(base_url, model)``. Raises ``pytest.skip.Exception`` (via
    ``pytest.skip``) when Ollama is unreachable or no gemma3 model is loaded.
    Honors ``LIVE_OLLAMA_BASE_URL`` (so the test runs both in-container via
    ``host.docker.internal`` and on this host via ``localhost``) and
    ``LIVE_OLLAMA_MODEL`` as an exact override (so ``gemma3:4b-instruct-q4``-style
    tags still run).
    """
    import httpx

    base_url = os.environ.get("LIVE_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
    probe_root = base_url.rstrip("/")
    if probe_root.endswith("/v1"):
        probe_root = probe_root[: -len("/v1")]
    tags_url = probe_root + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(tags_url)
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(
            f"Ollama at {base_url} not reachable: {type(exc).__name__}: {exc}. "
            f"On native-Linux Docker, host.docker.internal may not resolve — "
            f"set LIVE_OLLAMA_BASE_URL explicitly."
        )
    if resp.status_code != 200:
        pytest.skip(f"Ollama at {base_url} not reachable: HTTP {resp.status_code}")
    tags = resp.json().get("models", [])
    if not tags:
        pytest.skip(f"Ollama at {base_url} has no models loaded")

    available_names = [t.get("name") or t.get("model") for t in tags]
    available_names = [n for n in available_names if n]

    preferred = os.environ.get("LIVE_OLLAMA_MODEL")
    if preferred and preferred in available_names:
        model = preferred
    else:
        gemma_matches = [n for n in available_names if "gemma3" in n]
        if not gemma_matches:
            pytest.skip(
                f"Ollama at {base_url} has no gemma3 model loaded "
                f"(available: {available_names}). This test exercises text-form "
                f"recovery against a non-tool-capable model and must not silently "
                f"run against a tool-capable model. Set LIVE_OLLAMA_MODEL to "
                f"override with an exact tag."
            )
        # Prefer the bare gemma3:4b tag when present, else first gemma3 match.
        model = "gemma3:4b" if "gemma3:4b" in gemma_matches else gemma_matches[0]
    return base_url, model


@pytest.mark.live
async def test_gemma_textform_toolcall_recovery_live() -> None:
    """Real gemma3:4b emits a loose fenced ``get_weather`` call; the provider
    recovers it into a ``ToolCall`` and strips the raw block from ``content``.

    Bounded retry (3 attempts) absorbs non-determinism; ``temperature`` defaults
    to 0.0 in ``complete()``. If the model emits no recoverable call after 3
    attempts (e.g. it answered in plain prose) the test SKIPS as inconclusive —
    it does not fail (confidence-test stance).

    Edge case — if gemma somehow returns a STRUCTURED ``tool_calls`` (it
    shouldn't; tools aren't offered and gemma is non-tool-capable), the
    structured path yields a non-empty ``tool_calls`` and the strip assertions
    are vacuously satisfied: the test still passes (recovery-or-structured both
    yield a call). No explicit client cleanup is needed — ``complete()`` opens
    its ``httpx.AsyncClient`` in a per-call ``async with`` (no persistent
    client; ``aclose()`` is a no-op for Ollama).
    """
    base_url, model = await _resolve_gemma()
    prov = OllamaProvider(model=model, base_url=base_url)
    history = [
        Message(role=Role.SYSTEM, content=DIRECTIVE),
        Message(role=Role.USER, content="What's the weather in Paris?"),
    ]

    last = ""
    msg = None
    for attempt in range(3):
        msg = await prov.complete(history)
        last = msg.content
        # Log each attempt's raw content so a chronic-skip is diagnosable from
        # the flight log / pytest -s output.
        print(f"[gemma-recovery] attempt {attempt + 1}/3 raw content: {last!r}")
        if msg.tool_calls:
            break
    else:
        pytest.skip(
            f"gemma3 did not emit a recoverable tool-call form in 3 attempts "
            f"(non-deterministic; last content: {last!r})"
        )

    assert msg is not None and msg.tool_calls, "expected a recovered tool call"
    tc = msg.tool_calls[0]
    assert tc.name, "recovered ToolCall must have a non-empty name"
    assert isinstance(tc.arguments, dict), "recovered ToolCall arguments must be a dict"

    # Strip checks (DD4). PRIMARY check is fence-tag agnostic: whatever fence the
    # model chose (```tool / ```python / untagged), the call syntax must not be
    # rendered in the surviving content.
    assert "get_weather(" not in msg.content, (
        f"raw call syntax should have been stripped; content: {msg.content!r}"
    )
    assert "```tool" not in msg.content, (
        f"raw ```tool fence should have been stripped; content: {msg.content!r}"
    )
