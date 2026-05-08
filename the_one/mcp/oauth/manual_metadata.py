"""ManualOAuthClientProvider — non-DCR OAuth path.

For Authorization Servers that don't implement RFC 7591 Dynamic Client
Registration (e.g. GitHub at https://github.com/login/oauth), the
operator pre-registers an OAuth app at the IDP UI and pastes the
resulting ``client_id`` + auth/token endpoints into the chat-UI
manual-entry form.

This module's ``ManualOAuthClientProvider`` overrides
``OAuthClientProvider.async_auth_flow`` with a near-verbatim copy of
the parent body, eliding the three discovery/registration sections
that don't apply to the manual path:

  - Step 1 (RFC 9728 Protected Resource Metadata discovery)
  - Step 2 (RFC 8414 OAuth Authorization Server Metadata discovery)
  - Step 4 (Dynamic Client Registration sub-branch)

The override mirrors the FULL outer structure of the parent — outer
lock, ``_initialize`` call, protocol_version capture, refresh-retry,
initial yield, 401-handler-with-elisions, 403 step-up branch, final
``_add_auth_header + yield``. Only the three sections above are
elided/replaced.

SDK anchor (verified against ``mcp==1.27.0`` at design time):
``mcp.client.auth.oauth2.OAuthClientProvider.async_auth_flow`` —
``mcp/client/auth/oauth2.py`` lines 491-628 in the installed SDK. On
every ``mcp`` package upgrade, re-run ``A12`` (discovery short-circuit)
+ ``A12b`` (body-shape stake) tests in ``tests/test_oauth_manual_metadata.py``
before trusting this override; substring drift in the parent's body
triggers ``A12b`` and signals re-verification is required.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx
from mcp.client.auth.oauth2 import OAuthClientProvider, logger
from mcp.client.auth.utils import (
    extract_field_from_www_auth,
    extract_scope_from_www_auth,
    get_client_metadata_scopes,
)
from mcp.client.streamable_http import MCP_PROTOCOL_VERSION
from mcp.shared.auth import (
    OAuthClientInformationFull,
    OAuthMetadata,
)


@dataclass(frozen=True)
class ManualOAuthMetadata:
    """Operator-supplied OAuth endpoints for non-DCR-supporting AS.

    The chat-UI manual-entry form (L5) collects these three fields:
    the operator's pre-registered ``client_id`` plus the AS's auth +
    token endpoints. The synthesized ``OAuthMetadata`` derives an
    ``issuer`` URL via ``rsplit("/", 1)`` on ``auth_endpoint`` —
    informational only; the load-bearing fields are
    ``authorization_endpoint`` and ``token_endpoint``.
    """

    client_id: str
    auth_endpoint: str
    token_endpoint: str


class ManualOAuthClientProvider(OAuthClientProvider):
    """OAuthClientProvider variant that skips PRM/OASM discovery + DCR.

    See module docstring for the full elision list and SDK-version
    risk notes. Construction takes all the standard OAuthClientProvider
    args plus a keyword-only ``manual_metadata`` carrying the
    operator-supplied client_id + endpoints.
    """

    def __init__(
        self,
        *args,
        manual_metadata: ManualOAuthMetadata,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._manual_metadata = manual_metadata

    def _synthesized_oauth_metadata(self) -> OAuthMetadata:
        """Build the synthesized ``OAuthMetadata`` from manual-entry fields.

        Required-field set (verified at design time against
        ``mcp.shared.auth.OAuthMetadata``): ``issuer``,
        ``authorization_endpoint``, ``token_endpoint``. All other fields
        default per SDK; ``response_types_supported`` defaults to
        ``["code"]`` which matches our auth-code+PKCE flow.

        Issuer derivation (``rsplit("/", 1)``) is best-effort. For
        typical auth_endpoints (e.g. github's ``/login/oauth/authorize``)
        it gives a sensible issuer URL. For pathological shapes the
        derived issuer may be wrong but is non-fatal — the SDK uses
        ``issuer`` for informational purposes only; the load-bearing
        fields are the explicit auth + token endpoints.
        """
        issuer = self._manual_metadata.auth_endpoint.rsplit("/", 1)[0]
        return OAuthMetadata(
            issuer=issuer,
            authorization_endpoint=self._manual_metadata.auth_endpoint,
            token_endpoint=self._manual_metadata.token_endpoint,
        )

    def _synthesized_client_info(self) -> OAuthClientInformationFull:
        """Build the synthesized client_info from the manual ``client_id``.

        ``redirect_uris`` is passed through from
        ``self.context.client_metadata.redirect_uris`` so the AS issues
        the redirect to our loopback callback URL (configured at
        OAuthClientProvider construction time).
        """
        return OAuthClientInformationFull(
            client_id=self._manual_metadata.client_id,
            redirect_uris=self.context.client_metadata.redirect_uris,
        )

    async def _initialize(self) -> None:
        """Initialize bookkeeping + pre-set client_info from manual entry.

        Calls ``super()._initialize()`` first to load any persisted
        tokens + client_info, then injects the manual client_info if
        none is loaded so the 401-handler's DCR branch short-circuits
        on the ``if not self.context.client_info:`` guard.

        If a prior persisted client_info exists (from an earlier
        ``set_client_info`` call by the SDK after a previous successful
        flow), we leave it alone — this avoids clobbering operator-
        rotated credentials.
        """
        await super()._initialize()
        if not self.context.client_info:
            synthesized = self._synthesized_client_info()
            self.context.client_info = synthesized
            await self.context.storage.set_client_info(synthesized)

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Override of ``OAuthClientProvider.async_auth_flow``.

        Mirrors the parent body verbatim with three elisions in the 401
        handler: PRM discovery loop, OASM discovery loop, DCR sub-branch.
        See module docstring for SDK-version risk notes.
        """
        async with self.context.lock:
            if not self._initialized:
                await self._initialize()

            # Capture protocol version from request headers (parent verbatim)
            self.context.protocol_version = request.headers.get(MCP_PROTOCOL_VERSION)

            if not self.context.is_token_valid() and self.context.can_refresh_token():
                refresh_request = await self._refresh_token()
                refresh_response = yield refresh_request

                if not await self._handle_refresh_response(refresh_response):
                    self._initialized = False

            if self.context.is_token_valid():
                self._add_auth_header(request)

            response = yield request

            if response.status_code == 401:
                try:
                    # ELIDED — Step 1 (PRM discovery): manual path bypasses RFC 9728.
                    self.context.protected_resource_metadata = None

                    # ELIDED — Step 2 (OASM discovery): manual entry supplies metadata.
                    self.context.oauth_metadata = self._synthesized_oauth_metadata()

                    # Step 3 (scope selection) — preserved verbatim from parent.
                    # With protected_resource_metadata=None, scope falls back to
                    # extract_scope_from_www_auth(response) only — sufficient
                    # for manual-entry providers that don't advertise scopes via PRM.
                    self.context.client_metadata.scope = get_client_metadata_scopes(
                        extract_scope_from_www_auth(response),
                        self.context.protected_resource_metadata,
                        self.context.oauth_metadata,
                    )

                    # ELIDED — Step 4 DCR branch: client_info already pre-set in
                    # _initialize() above so the parent's
                    # ``if not self.context.client_info:`` guard short-circuits.

                    # Step 5 (auth + token exchange) — preserved verbatim from parent.
                    token_response = yield await self._perform_authorization()
                    await self._handle_token_response(token_response)
                except Exception:
                    logger.exception("OAuth flow error")
                    raise

                # Retry with new tokens — preserved verbatim from parent.
                self._add_auth_header(request)
                yield request
            elif response.status_code == 403:
                # 403 step-up scope reauth — preserved verbatim from parent
                # (no discovery in this branch; no override needed).
                error = extract_field_from_www_auth(response, "error")

                if error == "insufficient_scope":
                    try:
                        self.context.client_metadata.scope = get_client_metadata_scopes(
                            extract_scope_from_www_auth(response),
                            self.context.protected_resource_metadata,
                        )
                        token_response = yield await self._perform_authorization()
                        await self._handle_token_response(token_response)
                    except Exception:
                        logger.exception("OAuth flow error")
                        raise

                self._add_auth_header(request)
                yield request
