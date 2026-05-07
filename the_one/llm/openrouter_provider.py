"""OpenRouter provider — thin OpenAIProvider subclass.

Uses the OpenAI Python SDK against ``https://openrouter.ai/api/v1`` with
optional ranking headers (``HTTP-Referer``, ``X-Title``) and the empty-string
api_key opt-out so that ``OPENAI_API_KEY`` env var cannot leak into the
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

        # Empty-string opt-out (Decision 5): openai 2.15.0 reads
        # OPENAI_API_KEY ONLY when api_key is None. Coerce to "" so the
        # SDK skips the env fallback. Empty key → upstream 401 with a
        # clear message that the agent loop surfaces verbatim.
        resolved_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if resolved_key is None:
            resolved_key = ""

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
        # _enforce_credentials=False: openai>=2.16 raises OpenAIError when
        # api_key="" at construction time. We want the SDK to accept the empty
        # string and forward it; the upstream (openrouter.ai) returns a clean 401
        # so the agent loop surfaces the error without SDK-level noise.
        self.client = openai.AsyncOpenAI(**client_kwargs, _enforce_credentials=False)


register_provider("openrouter", OpenRouterProvider)
