"""Cross-provider validation that ``Message.usage.input_tokens`` grows
monotonically with conversation history.

F6 L06 HAT (M08 KI #2): operator observed Ollama reporting flat
``prompt_tokens`` around ~1000 after a multi-turn qwen conversation.
The agent sends full history every turn (``the_one/agent/core.py``
appends each turn's messages without truncation), so a flat
prompt-token count means the provider is undercounting. This harness
localizes the symptom: if Ollama undercounts AND another provider on
the same conversation shape reports growing counts, the issue is
Ollama-side. If all providers undercount, our request shape is at
fault.

Marker: ``@pytest.mark.live`` — deselected from default CI. Run with
``pytest -m live`` and the relevant provider credentials set in env.

Operator invocation examples (run from inside the ``the-one``
container, or via ``docker exec``):

    # Single provider
    docker exec -e ANTHROPIC_API_KEY=sk-... the-one \\
        pytest -m live \\
        tests/test_input_tokens_cross_provider_live.py::test_anthropic_input_tokens_monotonic -v

    # All available providers (each test self-skips when its
    # credentials are absent)
    docker exec -e ANTHROPIC_API_KEY=sk-... \\
        -e OPENAI_API_KEY=sk-... \\
        -e LIVE_OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \\
        -e OPENROUTER_API_KEY=sk-or-... \\
        the-one pytest -m live \\
        tests/test_input_tokens_cross_provider_live.py -v

Per-provider model overrides (useful when the default model isn't
accessible to the operator's API-key family):

    LIVE_ANTHROPIC_MODEL   (default: claude-haiku-4-5-20251001)
    LIVE_OPENAI_MODEL      (default: gpt-4o-mini)
    LIVE_OLLAMA_MODEL      (default: qwen2.5:7b if present, else first
                           model returned by /api/tags)
    LIVE_OPENROUTER_MODEL  (default: meta-llama/llama-3.2-3b-instruct:free)

Cost: each test runs 3 real LLM calls with short prompts. Cheap-model
defaults keep this minimal; operator should verify their selected
model in the provider's pricing docs.

Scope distinction vs ``tests/test_aiat.py``: ``test_aiat.py`` also uses
``@pytest.mark.live`` but exercises the running service over HTTP
(end-to-end agent loop). This module is a NARROWER diagnostic — it
instantiates providers directly and bypasses the agent loop entirely,
so any token-count anomaly is attributable to the provider's
``usage`` reporting rather than agent-side history shaping.
"""
from __future__ import annotations

import os

import pytest

from the_one.llm.base import Message


async def _aclose_provider_client(provider) -> None:
    """Best-effort async teardown of a provider's HTTP client.

    Anthropic + OpenAI + OpenRouter providers all hold an SDK client at
    ``provider.client`` whose ``aclose()`` releases the underlying
    connection pool. Ollama provider uses a fresh ``httpx.AsyncClient``
    per call (no persistent client to close). We swallow attribute /
    runtime errors here — teardown is best-effort and must not mask the
    test result.
    """
    client = getattr(provider, "client", None)
    if client is None:
        return
    aclose = getattr(client, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception:
        # Teardown failures must not poison the test outcome.
        pass


async def _run_three_turn_conversation(provider, model_label: str) -> list[int]:
    """Run a 3-turn conversation through ``provider.complete``.

    Returns ``[input_tokens turn1, turn2, turn3]``. Each turn appends
    the new user message AND the previous assistant response to the
    running message list, mirroring how ``the_one/agent/core.py`` ships
    full history every turn.
    """
    prompts = [
        "Reply with the single word: hello.",
        "Now reply with the single word: world.",
        "Now reply with the single word: again.",
    ]
    messages: list[Message] = []
    counts: list[int] = []
    for user_text in prompts:
        messages.append(Message.user(user_text))
        response = await provider.complete(messages=messages)
        assert response.usage is not None, (
            f"{model_label}: no usage reported by provider"
        )
        counts.append(response.usage.input_tokens)
        messages.append(response)  # assistant turn enters history for next call
    return counts


def _assert_monotonic_growth(counts: list[int], provider_name: str, model: str) -> None:
    assert all(c > 0 for c in counts), (
        f"{provider_name}/{model}: input_tokens not positive for all turns: "
        f"{counts}. Provider may be returning zeroed usage (tokenizer "
        f"misconfigured?) — this is the F6 KI #2 symptom in degenerate form."
    )
    assert counts[0] <= counts[1] <= counts[2], (
        f"{provider_name}/{model}: input_tokens NOT monotonically non-decreasing "
        f"across 3 turns: {counts}. "
        f"This is the F6 KI #2 symptom — the provider is undercounting prompt "
        f"tokens. If only Ollama shows this, the bug is Ollama-side. If "
        f"multiple providers show this, the agent's request shape is at fault."
    )


def _skip_on_auth_error(provider_name: str, exc: Exception) -> None:
    """Translate provider auth/permission errors into a pytest skip.

    Operators sometimes hold API keys scoped to a model family that
    doesn't include the default model. Rather than failing the test
    (which would be a false-positive for token-monotonicity), we skip
    with a hint pointing at the ``LIVE_{PROVIDER}_MODEL`` env-var
    override.
    """
    pytest.skip(
        f"{provider_name}: auth/permission error from provider — "
        f"{type(exc).__name__}: {exc}. "
        f"If your API key is scoped to a specific model family, set "
        f"LIVE_{provider_name.upper()}_MODEL to a model that key can access."
    )


@pytest.mark.live
async def test_anthropic_input_tokens_monotonic() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip(
            "ANTHROPIC_API_KEY not set — operator must export the key to run "
            "this live test"
        )
    try:
        import anthropic
    except ImportError:
        pytest.skip("anthropic SDK not installed")
    from the_one.llm.anthropic_provider import AnthropicProvider

    model = os.environ.get("LIVE_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    provider = AnthropicProvider(model=model)
    try:
        try:
            counts = await _run_three_turn_conversation(
                provider, f"anthropic/{model}"
            )
        except (
            anthropic.PermissionDeniedError,
            anthropic.AuthenticationError,
        ) as exc:
            _skip_on_auth_error("anthropic", exc)
            return
        _assert_monotonic_growth(counts, "anthropic", model)
    finally:
        await _aclose_provider_client(provider)


@pytest.mark.live
async def test_openai_input_tokens_monotonic() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip(
            "OPENAI_API_KEY not set — operator must export the key to run "
            "this live test"
        )
    try:
        import openai
    except ImportError:
        pytest.skip("openai SDK not installed")
    from the_one.llm.openai_provider import OpenAIProvider

    model = os.environ.get("LIVE_OPENAI_MODEL", "gpt-4o-mini")
    provider = OpenAIProvider(model=model)
    try:
        try:
            counts = await _run_three_turn_conversation(
                provider, f"openai/{model}"
            )
        except (
            openai.PermissionDeniedError,
            openai.AuthenticationError,
        ) as exc:
            _skip_on_auth_error("openai", exc)
            return
        _assert_monotonic_growth(counts, "openai", model)
    finally:
        await _aclose_provider_client(provider)


@pytest.mark.live
async def test_ollama_input_tokens_monotonic() -> None:
    base_url = os.environ.get(
        "LIVE_OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"
    )
    import httpx

    # Probe Ollama via /api/tags (NOT the OpenAI-compat /v1 prefix). Strip a
    # trailing /v1 if present so the same env var works whether the operator
    # points at the bare host or the OpenAI-compat endpoint.
    probe_root = base_url.rstrip("/")
    if probe_root.endswith("/v1"):
        probe_root = probe_root[: -len("/v1")]
    tags_url = probe_root + "/api/tags"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
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

    # Prefer LIVE_OLLAMA_MODEL → qwen2.5:7b (F6 bug-report scenario) → first
    # available.
    preferred = os.environ.get("LIVE_OLLAMA_MODEL")
    available_names = [t.get("name") or t.get("model") for t in tags]
    available_names = [n for n in available_names if n]
    if preferred and preferred in available_names:
        model = preferred
    elif "qwen2.5:7b" in available_names:
        model = "qwen2.5:7b"
    elif available_names:
        model = available_names[0]
    else:
        pytest.skip(f"Ollama at {base_url} returned tags but no model names")

    from the_one.llm.ollama_provider import OllamaProvider

    provider = OllamaProvider(model=model, base_url=base_url)
    try:
        try:
            counts = await _run_three_turn_conversation(
                provider, f"ollama/{model}"
            )
        except (httpx.HTTPStatusError, httpx.HTTPError) as exc:
            # Ollama auth/permission failures surface as HTTP errors (no
            # SDK exception hierarchy to discriminate against).
            _skip_on_auth_error("ollama", exc)
            return
        _assert_monotonic_growth(counts, "ollama", model)
    finally:
        await _aclose_provider_client(provider)


@pytest.mark.live
async def test_openrouter_input_tokens_monotonic() -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        pytest.skip(
            "OPENROUTER_API_KEY not set — operator must export the key to "
            "run this live test"
        )
    try:
        import openai
    except ImportError:
        pytest.skip("openai SDK (required by OpenRouter provider) not installed")
    from the_one.llm.openrouter_provider import OpenRouterProvider

    model = os.environ.get(
        "LIVE_OPENROUTER_MODEL", "meta-llama/llama-3.2-3b-instruct:free"
    )
    provider = OpenRouterProvider(model=model)
    try:
        try:
            counts = await _run_three_turn_conversation(
                provider, f"openrouter/{model}"
            )
        except (
            openai.PermissionDeniedError,
            openai.AuthenticationError,
        ) as exc:
            _skip_on_auth_error("openrouter", exc)
            return
        _assert_monotonic_growth(counts, "openrouter", model)
    finally:
        await _aclose_provider_client(provider)
