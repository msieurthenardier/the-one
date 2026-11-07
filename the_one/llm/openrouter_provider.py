"""OpenRouter provider — thin OpenAIProvider subclass.

Uses the OpenAI Python SDK against ``https://openrouter.ai/api/v1`` with
fixed ranking headers (``HTTP-Referer``, ``X-Title``) identifying this
app, plus a non-empty api_key placeholder so that ``OPENAI_API_KEY`` env
var cannot leak into the OpenRouter client.

The constructor deliberately does NOT call ``super().__init__()``; that
would trigger the OpenAI SDK env-var fallback.

#122 route asymmetry (Flight 4, DD3). On an ``anthropic/*`` route a tool whose
``input_schema`` is *genuinely unsanitizable* is forwarded unmodified with a
WARN (see ``tool_schema`` below) — it is *not* dropped, unlike the
Anthropic-direct path (``anthropic_provider.py`` DD5 drop-and-proceed). This is
an intentional minimal-scope decision: the common ``anyOf``/``oneOf``/``allOf``
case is fixed on *both* paths; only the rare unsanitizable case diverges, where
forwarding is no worse than today (the request 400s at the backend exactly as it
did pre-fix). Pinned by the forward-with-WARN test in the cross-provider
conformance suite (``tests/test_llm_provider_cross_provider_conformance.py``).
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

import httpx
import openai

from the_one.llm import openrouter_api
from the_one.llm._schema_sanitize import UnsanitizableToolSchema, sanitize_tool_schema
from the_one.llm.openai_provider import DEFAULT_OPENAI_TIMEOUT, OpenAIProvider
from the_one.llm.registry import register_provider

logger = logging.getLogger(__name__)

# F7 L04: per-provider bytes-per-token for the mid-stream usage byte-
# heuristic. Most OpenRouter-routed models are OpenAI-compat, so the
# tokeniser density matches the OpenAI default. Exposed as a module-
# level constant so the override is visible at a glance — the class-level
# ``bytes_per_token`` accessor below is set to this value.
BYTES_PER_TOKEN_OPENROUTER = 4.0


# App identity for OpenRouter's ranking-header leaderboard. Hardcoded
# because these identify *this app* (GleepGlorp AI), not the operator;
# the operator running GleepGlorp AI is by definition running this app.
#
# Asymmetry note (Mission 08 constraint): the repo / module name stays
# ``the-one`` (rename out of scope for the rebrand mission), but the
# *display* identity that OpenRouter surfaces on its X-Title-driven app
# leaderboard is the user-facing brand. The URL therefore preserves the
# original GitHub slug while the name reflects the brand.
# GleepGlorp AI — repo slug preserved per M08 rename-scope constraint.
_APP_URL = "https://github.com/msieurthenardier/the-one"
_APP_NAME = "GleepGlorp AI"


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"
    # M16 F08 L01 (MEDIUM-1): single source of truth, replacing the prior
    # ``_bytes_per_token_for_interim`` override. Most routed models are
    # OpenAI-compat (cl100k_base) so the density matches OpenAI's; kept as a
    # distinct constant so a future per-route tuning pass can diverge without
    # disturbing OpenAI direct-API.
    bytes_per_token = BYTES_PER_TOKEN_OPENROUTER

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
        config: dict | None = None,  # A4 keys read via _read_a4_config; referer/title hardcoded
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

        # M16 F11 L03: read the A4 request params (reasoning_effort /
        # response_format / stop) from this constructor's own explicit
        # ``config`` param. OpenAIProvider.__init__ is never called (see
        # above), so this must be done here directly rather than inherited —
        # keeps the instance-attr parity contract
        # (test_subclass_has_all_parent_instance_attrs) satisfied.
        self._read_a4_config(config)

        # M08 F7 L05 (F6.5 debrief AI #1): defuse the manual-state-mirror
        # tripwire. Any future instance state added to
        # ``LLMProvider._init_provider_state`` is automatically inherited
        # by this provider without having to mirror it here. Required
        # because we intentionally skip ``super().__init__()`` above
        # (Decision 5: no-leak invariant on OPENAI_API_KEY).
        self._init_provider_state()

    def tool_schema(self, tool_def: dict[str, Any]) -> dict[str, Any]:
        result = super().tool_schema(tool_def)  # OpenAI function shape
        # #122: OpenRouter forwards tool schemas verbatim to the provider
        # backend; the Anthropic backend (incl. via Bedrock) rejects a
        # top-level oneOf/allOf/anyOf. Sanitize only for anthropic/* routes —
        # other backends accept the combinators and we must not degrade them.
        if self.model.startswith("anthropic/"):
            try:
                result["function"]["parameters"] = sanitize_tool_schema(
                    result["function"].get("parameters")
                )
            except UnsanitizableToolSchema as exc:
                # Minimal scope (operator 2026-06-18): no DD5 drop-and-proceed
                # on this path. Leave the original schema so the request 400s
                # at the API exactly as today — no worse than pre-fix. Warn so
                # the otherwise-silent #122 rejection is diagnosable (this is
                # observability, NOT drop-and-proceed — the tool is still sent).
                logger.warning(
                    "Tool %r has an input_schema that cannot be sanitized for the "
                    "Anthropic route %r (%s); sending it unmodified — the Anthropic "
                    "backend will likely reject it (#122).",
                    tool_def.get("name", "<unnamed>"),
                    self.model,
                    exc.reason,
                )
        return result

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
            self.context_window_known = True
        # else: leave at class default (128k); the wrapper catches errors
        # from the helper and flips the sentinel either way.

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
