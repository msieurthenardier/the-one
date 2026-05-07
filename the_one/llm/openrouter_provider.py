"""OpenRouter provider — thin OpenAIProvider subclass.

Uses the OpenAI Python SDK against ``https://openrouter.ai/api/v1`` with
optional ranking headers (``HTTP-Referer``, ``X-Title``) and a non-empty
api_key placeholder so that ``OPENAI_API_KEY`` env var cannot leak into the
OpenRouter client.

The constructor deliberately does NOT call ``super().__init__()``; that
would trigger the OpenAI SDK env-var fallback. See
``test_instance_attribute_parity`` — if a parent attribute is added later,
that test fails and forces a sync.
"""

from __future__ import annotations

import os
from typing import Any

import openai

from the_one.llm.openai_provider import OpenAIProvider
from the_one.llm.registry import register_provider

# Sentinel that fills the api_key when neither the constructor arg nor
# OPENROUTER_API_KEY is set. Decision 5 originally specified an
# empty-string opt-out, but openai>=2.16 raises ``OpenAIError`` on
# ``api_key=""`` at construction time and the only escape (the private
# ``_enforce_credentials=False`` kwarg) is unsafe to depend on. A
# non-empty placeholder satisfies the SDK's public contract; OpenRouter
# returns a clean 401 with the placeholder in the bearer header, and
# the agent loop surfaces that error verbatim.
_NO_KEY_PLACEHOLDER = "openrouter-no-key-set"


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"

    def __init__(
        self,
        model: str = "",
        api_key: str | None = None,
        base_url: str = "https://openrouter.ai/api/v1",
        config: dict | None = None,
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
            resolved_key = _NO_KEY_PLACEHOLDER

        cfg = config or {}
        headers: dict[str, str] = {}
        # referer / title are validated at the POST /api/providers
        # boundary (Decision 6); this code trusts the saved value but
        # still skips empty strings so absent headers stay absent.
        if cfg.get("referer"):
            headers["HTTP-Referer"] = cfg["referer"]
        if cfg.get("title"):
            headers["X-Title"] = cfg["title"]

        client_kwargs: dict[str, Any] = {"api_key": resolved_key, "base_url": base_url}
        if headers:
            client_kwargs["default_headers"] = headers
        self.client = openai.AsyncOpenAI(**client_kwargs)


register_provider("openrouter", OpenRouterProvider)
