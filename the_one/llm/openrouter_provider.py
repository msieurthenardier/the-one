"""OpenRouter provider — thin OpenAIProvider subclass.

Uses the OpenAI Python SDK against ``https://openrouter.ai/api/v1`` with
fixed ranking headers (``HTTP-Referer``, ``X-Title``) identifying this
app, plus a non-empty api_key placeholder so that ``OPENAI_API_KEY`` env
var cannot leak into the OpenRouter client.

The constructor deliberately does NOT call ``super().__init__()``; that
would trigger the OpenAI SDK env-var fallback.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

import httpx
import openai

from the_one.llm import openrouter_api
from the_one.llm.openai_provider import DEFAULT_OPENAI_TIMEOUT, OpenAIProvider
from the_one.llm.registry import register_provider

# F7 L04: per-provider bytes-per-token for the mid-stream usage byte-
# heuristic. Most OpenRouter-routed models are OpenAI-compat, so the
# tokeniser density matches the OpenAI default. Exposed as a module-
# level constant so the override is visible at a glance — the
# ``_bytes_per_token_for_interim`` override below returns this value.
BYTES_PER_TOKEN_OPENROUTER = 4.0


# App identity for OpenRouter's ranking-header leaderboard. Hardcoded
# because these identify *this app* (the-one), not the operator; the
# operator running the-one is by definition running the-one. A future
# rebranding mission consolidates this with the other "the-one" / "0.1"
# strings scattered across cli.py, web/app.py, mcp/* into a single
# identity module.
_APP_URL = "https://github.com/msieurthenardier/the-one"
_APP_NAME = "the-one"


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"

    # Sentinel that fills the api_key when neither the constructor arg
    # nor OPENROUTER_API_KEY is set. Decision 5 originally specified an
    # empty-string opt-out, but openai>=2.16 raises ``OpenAIError`` on
    # ``api_key=""`` at construction time and the only escape (the
    # private ``_enforce_credentials=False`` kwarg) is unsafe to depend
    # on. A non-empty placeholder satisfies the SDK's public contract;
    # OpenRouter returns a clean 401 with the placeholder in the bearer
    # header, and the agent loop surfaces that error verbatim.
    #
    # ClassVar — subclasses can override the placeholder string without
    # reaching for a module-level global. Tests prefer the qualified
    # access (``OpenRouterProvider._NO_KEY_PLACEHOLDER``) over importing
    # a module-level constant so the contract belongs to the class, not
    # the file.
    _NO_KEY_PLACEHOLDER: ClassVar[str] = "openrouter-no-key-set"

    def __init__(
        self,
        model: str = "",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        config: dict | None = None,  # accepted for factory uniformity; unused
        timeout: httpx.Timeout | None = None,
        **kwargs: Any,
    ):
        # Override constructor entirely — do NOT call super().__init__() —
        # so the parent's OPENAI_API_KEY env-var fallback does not leak to
        # OpenRouter. Pinned by test_no_leak_with_api_key_none.
        self.model = model

        # No-leak invariant (Decision 5): the openai SDK reads
        # OPENAI_API_KEY ONLY when ``api_key is None``. We never let
        # ``None`` reach the SDK constructor; if both the explicit arg
        # and OPENROUTER_API_KEY are unset, we pass _NO_KEY_PLACEHOLDER.
        # Empty-string is also a no-no on openai>=2.16 (raises at
        # construction). The placeholder is public-API-clean and produces
        # an obvious 401 upstream.
        resolved_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if resolved_key is None or resolved_key == "":
            resolved_key = self._NO_KEY_PLACEHOLDER

        client_kwargs: dict[str, Any] = {
            "api_key": resolved_key,
            "base_url": base_url,
            "timeout": timeout if timeout is not None else DEFAULT_OPENAI_TIMEOUT,
            "default_headers": {
                "HTTP-Referer": _APP_URL,
                "X-Title": _APP_NAME,
            },
        }
        self.client = openai.AsyncOpenAI(**client_kwargs)

        # Stash the resolved-but-pre-placeholder key for capability lookups.
        # Passing ``_NO_KEY_PLACEHOLDER`` to ``openrouter_api`` would just
        # waste a cache slot — ``/models`` is publicly accessible without
        # auth — so we record None when no real key was provided.
        self._lookup_api_key: str | None = (
            api_key
            if (api_key is not None and api_key != "")
            else os.environ.get("OPENROUTER_API_KEY")
        )
        self._lookup_base_url = base_url

        # M08 F7 L05 (F6.5 debrief AI #1): defuse the manual-state-mirror
        # tripwire. Any future instance state added to
        # ``LLMProvider._init_provider_state`` is automatically inherited
        # by this provider without having to mirror it here. Required
        # because we intentionally skip ``super().__init__()`` above
        # (Decision 5: no-leak invariant on OPENAI_API_KEY).
        self._init_provider_state()

    async def _resolve_max_context_tokens(self) -> None:
        # Override OpenAIProvider's prefix-table resolver — OpenRouter
        # exposes ``context_length`` directly on the /models listing, so
        # we read it there rather than maintain a parallel table.
        resolved = await openrouter_api.get_model_context_length(
            self._lookup_base_url,
            self._lookup_api_key,
            self.model,
        )
        if resolved is not None and resolved > 0:
            self.max_context_tokens = resolved
        # else: leave at class default (128k); the wrapper catches errors
        # from the helper and flips the sentinel either way.

    def _bytes_per_token_for_interim(self) -> float:
        """F7 L04: OpenRouter override. Most routed models are
        OpenAI-compat (cl100k_base tokeniser) so the density matches the
        OpenAI default; exposed as a separate constant so a future tuning
        pass can adjust per-route without disturbing OpenAI direct-API.
        """
        return BYTES_PER_TOKEN_OPENROUTER

    async def supports_tools(self) -> bool:
        """Return False if the OpenRouter model is known not to advertise
        ``tools`` in its ``supported_parameters``. Returns True when
        capabilities can't be determined (network blip, model missing,
        non-functional key) so the request still goes out — mirrors
        ``OllamaProvider.supports_tools`` fail-open semantics.
        """
        caps = await openrouter_api.get_model_capabilities(
            self._lookup_base_url,
            self._lookup_api_key,
            self.model,
        )
        return caps is None or "tools" in caps


register_provider("openrouter", OpenRouterProvider)
