"""Anthropic plan provider — bearer-token subclass of AnthropicProvider.

M19 F01 DD-4 (skeleton half): ``AnthropicPlanProvider`` overrides ONLY the
SDK-client construction seam (``_build_client``) to authenticate with a
consumer-OAuth access token (``auth_token`` bearer mode + the
``anthropic-beta: oauth-2025-04-20`` header) instead of an API key.
Everything else — ``_build_kwargs``, streaming, thinking capture/replay,
tool schema sanitization, temperature retry — is inherited. Mirrors the
``OpenRouterProvider(OpenAIProvider)`` precedent.

M19 F01 L02 (DD-3 half): tokens are fed by the self-resolving credential
source keyed by ``provider_config_id``. The ``_before_request`` hook
(awaited by the parent at the top of ``complete()``/``stream()``) obtains
a fresh access token from ``plan_credentials.get_credential_source`` and
applies it via **in-place ``client.auth_token`` mutation** — design-review
verified against anthropic SDK 0.96.0 (``_bearer_auth`` is a property read
per-request via ``_build_headers``; nothing is cached at construction) and
premise-pinned by ``tests/test_anthropic_provider.py``.

Precedence: an explicit ``access_token`` constructor kwarg (tests,
conformance suites, back-door feeds) WINS over source resolution — the
hook short-circuits and the registry is never consulted. A provider with
neither a static token nor stored credentials raises the typed
:class:`~the_one.llm.plan_credentials.ReauthRequiredError` at
``_before_request`` time (actionable, not a bare SDK auth error).
"""

from __future__ import annotations

from typing import Any

import anthropic

from the_one.llm.anthropic_provider import AnthropicProvider
from the_one.llm.registry import register_provider

# Beta flag Anthropic requires for consumer-OAuth (plan) bearer tokens.
OAUTH_BETA_HEADER = "oauth-2025-04-20"


class AnthropicPlanProvider(AnthropicProvider):
    name = "anthropic-plan"

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        *,
        access_token: str | None = None,
        provider_config_id: str | None = None,
        **kwargs: Any,
    ):
        # Stashed BEFORE super().__init__ because the parent constructor
        # calls _build_client(), which reads _access_token.
        self._access_token = access_token
        # Leg 2's credential source resolves by this id; stored now so the
        # constructor surface is final for all construction sites.
        self.provider_config_id = provider_config_id
        super().__init__(model=model, api_key=api_key, **kwargs)

    def _build_client(self, api_key: str | None) -> anthropic.AsyncAnthropic:
        """Bearer-token client: ``auth_token`` + OAuth beta header.

        ``api_key=None`` is passed EXPLICITLY (and re-forced below) so the
        SDK's ``ANTHROPIC_API_KEY`` env fallback can never put this client
        into ``x-api-key`` mode — plan providers authenticate with the
        OAuth bearer token only. The stored-config ``api_key`` arg is
        deliberately ignored.
        """
        client = anthropic.AsyncAnthropic(
            api_key=None,
            auth_token=self._access_token,
            default_headers={"anthropic-beta": OAUTH_BETA_HEADER},
        )
        # The SDK constructor falls back to os.environ["ANTHROPIC_API_KEY"]
        # when api_key is None; null it out so bearer mode is unconditional.
        client.api_key = None
        return client

    async def _before_request(self) -> None:
        """Ensure a fresh OAuth access token before every request (DD-3/DD-4).

        - Explicit ``access_token`` kwarg wins: static-token providers
          (tests, conformance) never consult the credential-source
          registry — short-circuit.
        - Otherwise resolve the process-wide credential source by
          ``provider_config_id`` and apply its token by mutating
          ``client.auth_token`` in place (SDK 0.96.0 reads the bearer
          header per-request; see module docstring). The source refreshes
          proactively / single-flight and raises the typed
          ``ReauthRequiredError`` on terminal failure — which propagates
          from here so agents fail actionably instead of with a bare SDK
          auth error.
        """
        if self._access_token is not None:
            return
        # Lazy import: keeps the module importable without touching the
        # credential-source machinery for static-token construction, and
        # mirrors the registry's lazy-load style.
        from the_one.llm.plan_credentials import ReauthRequiredError, get_credential_source

        if self.provider_config_id is None:
            raise ReauthRequiredError(
                "<unsaved>",
                (
                    "Anthropic plan provider was constructed without an access "
                    "token or a provider config id — sign in to the provider "
                    "in Administration and rebuild the agent."
                ),
            )
        source = get_credential_source(self.provider_config_id)
        self.client.auth_token = await source.get_access_token()


register_provider("anthropic-plan", AnthropicPlanProvider)
