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
from typing import Any, ClassVar

import httpx
import openai

from the_one.llm import openrouter_api
from the_one.llm.openai_provider import DEFAULT_OPENAI_TIMEOUT, OpenAIProvider
from the_one.llm.registry import register_provider


_FORBIDDEN_HEADER_CHARS = ("\r", "\n", "\x00")


def _assert_safe_header(name: str, value: str) -> None:
    """Reject CR/LF/NUL in header values. The API write boundary
    (``_validate_openrouter_config``) rejects these with a 422; this
    constructor-level check is defense-in-depth so any future code path
    that bypasses the API (CLI, scripts, tests, programmatic creation)
    can't smuggle a header injection through. httpx 0.28.1 sends control
    chars verbatim — so the constructor is the right boundary to refuse
    them at type-construction time."""
    for ch in _FORBIDDEN_HEADER_CHARS:
        if ch in value:
            raise ValueError(
                f"OpenRouter {name} contains forbidden control character "
                f"{ch!r}; refused at constructor."
            )


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
        config: dict | None = None,
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

        cfg = config or {}
        headers: dict[str, str] = {}
        # referer / title are validated at the POST /api/providers
        # boundary (Decision 6); this code trusts the saved value but
        # still skips empty strings so absent headers stay absent. The
        # CR/LF/NUL check below is defense-in-depth so any code path
        # that bypasses the API write boundary can't smuggle a header
        # injection through (review C3 + type-design recommendation).
        if cfg.get("referer"):
            _assert_safe_header("referer", cfg["referer"])
            headers["HTTP-Referer"] = cfg["referer"]
        if cfg.get("title"):
            _assert_safe_header("title", cfg["title"])
            headers["X-Title"] = cfg["title"]

        client_kwargs: dict[str, Any] = {
            "api_key": resolved_key,
            "base_url": base_url,
            "timeout": timeout if timeout is not None else DEFAULT_OPENAI_TIMEOUT,
        }
        if headers:
            client_kwargs["default_headers"] = headers
        self.client = openai.AsyncOpenAI(**client_kwargs)

        # Stash the resolved-but-pre-placeholder key for capability lookups.
        # Passing ``_NO_KEY_PLACEHOLDER`` to ``openrouter_api`` would just
        # waste a cache slot — ``/models`` is publicly accessible without
        # auth — so we record None when no real key was provided.
        self._lookup_api_key: str | None = (
            api_key if (api_key is not None and api_key != "")
            else os.environ.get("OPENROUTER_API_KEY")
        )
        self._lookup_base_url = base_url

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
