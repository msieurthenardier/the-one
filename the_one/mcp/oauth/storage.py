"""TokenStorage Protocol implementation backed by MCPSourceRepository.

Persists OAuth tokens and DCR client_info into the four named keys of an
``MCPSource.secrets`` dict:

  - ``access_token``      — str (the bearer token)
  - ``refresh_token``     — str | None
  - ``token_expires_at``  — float (Unix epoch seconds at issuance + expires_in)
  - ``dcr_credentials``   — dict | None (full ``OAuthClientInformationFull``
                            JSON, plus a ``registration_method`` discriminator
                            so L4 can pick the right provider class)

The SDK's ``OAuthToken.expires_in`` is a relative duration (seconds at
issuance, NOT a Unix epoch). The storage layer translates between the
SDK's relative form and our persisted absolute form via ``time.time()``
on read/write.

Race contract (cycle-2 M5): ``set_tokens`` writes are last-writer-wins.
Two parallel ``set_tokens`` calls (e.g. from two parallel tool
invocations on the same MCP source) both ``repo.update`` the row; the
second write clobbers the first. Because both calls typically write the
SAME fresh tokens (parallel refresh requests using the same expired
access token typically receive the same new tokens from the AS), the
race is observable only as wasted writes, not as lost data.
"""

from __future__ import annotations

import time
from typing import Any

from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from the_one.db.repositories import MCPSourceRepository


class MCPSourceTokenStorage(TokenStorage):
    """TokenStorage Protocol impl backed by MCPSourceRepository.

    Reads/writes the four OAuth-managed secrets keys on a single
    MCPSource row identified by ``source_id``. Construction is cheap
    (no I/O); all I/O happens inside the four async methods. Each
    method does one ``repo.get`` then optionally one ``repo.update``.

    The four managed secret keys are protected from operator overwrite
    by the ``_OAUTH_MANAGED_SECRET_KEYS`` strip+preserve logic in
    ``the_one/interfaces/web/api.py`` — only this storage layer (and
    direct DB writes, which are unsupported) writes them.
    """

    def __init__(self, repo: MCPSourceRepository, source_id: str) -> None:
        self._repo = repo
        self._source_id = source_id

    async def get_tokens(self) -> OAuthToken | None:
        """Load the persisted token, translating ``expires_at`` → ``expires_in``.

        Returns None if no ``access_token`` is stored. Partial state
        (e.g. ``access_token`` without ``refresh_token``) returns a
        valid ``OAuthToken`` with ``refresh_token=None``. Malformed
        ``token_expires_at`` (string, etc.) is treated as "no expiry
        info" — ``expires_in=None`` — which forces a refresh-on-next-call
        rather than crashing.
        """
        source = await self._repo.get(self._source_id)
        access = source.secrets.get("access_token")
        if not access:
            return None
        expires_at = source.secrets.get("token_expires_at")
        expires_in: int | None = None
        if isinstance(expires_at, (int, float)):
            expires_in = max(0, int(expires_at - time.time()))
        return OAuthToken(
            access_token=access,
            token_type=source.secrets.get("token_type", "Bearer"),
            expires_in=expires_in,
            refresh_token=source.secrets.get("refresh_token"),
            scope=source.secrets.get("scope"),
        )

    async def set_tokens(self, tokens: OAuthToken) -> None:
        """Persist a token to the four managed keys.

        Translates ``expires_in`` (relative seconds at issuance) to
        ``token_expires_at`` (absolute Unix epoch). If the SDK passes
        ``expires_in=None``, any previously stored ``token_expires_at``
        is cleared so the read path returns ``expires_in=None``.

        Refresh-token rotation: a second call with a NEW token
        overwrites BOTH ``access_token`` AND ``refresh_token`` in a
        single ``repo.update`` round-trip.
        """
        source = await self._repo.get(self._source_id)
        secrets: dict[str, Any] = dict(source.secrets)
        secrets["access_token"] = tokens.access_token
        secrets["token_type"] = tokens.token_type
        if tokens.refresh_token is not None:
            secrets["refresh_token"] = tokens.refresh_token
        if tokens.scope is not None:
            secrets["scope"] = tokens.scope
        if tokens.expires_in is not None:
            secrets["token_expires_at"] = time.time() + tokens.expires_in
        elif "token_expires_at" in secrets:
            del secrets["token_expires_at"]
        source.secrets = secrets
        await self._repo.update(source)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        """Load the persisted DCR client_info, if any.

        Stored under ``secrets["dcr_credentials"]`` as a JSON dict
        plus a ``registration_method`` discriminator (``"dcr"`` or
        ``"manual"``) the L4 connect path uses to pick the right
        provider class.
        """
        source = await self._repo.get(self._source_id)
        creds = source.secrets.get("dcr_credentials")
        if not isinstance(creds, dict):
            return None
        # The discriminator is OUR field, not part of the SDK schema —
        # strip it before validating against OAuthClientInformationFull.
        payload = {k: v for k, v in creds.items() if k != "registration_method"}
        if not payload:
            return None
        try:
            return OAuthClientInformationFull.model_validate(payload)
        except Exception:
            # Corrupt persisted credentials — return None so the next
            # auth flow re-registers from scratch. Logging is the L4
            # connect path's responsibility (it knows the source_id).
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        """Persist DCR client_info under ``secrets["dcr_credentials"]``.

        The ``registration_method`` discriminator defaults to ``"dcr"``;
        ``ManualOAuthClientProvider`` overrides ``set_client_info`` (or
        sets the discriminator at registration time) to mark its
        synthesized client_info as ``"manual"``. Future L4 connect-path
        logic reads this field to decide whether to construct a
        ``ManualOAuthClientProvider`` vs the default
        ``OAuthClientProvider``.
        """
        source = await self._repo.get(self._source_id)
        secrets: dict[str, Any] = dict(source.secrets)
        payload = client_info.model_dump(mode="json", exclude_none=False)
        # Preserve the discriminator if the prior store had one, else
        # default to "dcr". The manual-entry path should overwrite this
        # via a follow-up ``set_client_info`` whose stored payload has
        # ``registration_method="manual"`` — see manual_metadata.py.
        prior = secrets.get("dcr_credentials")
        if isinstance(prior, dict) and prior.get("registration_method"):
            payload["registration_method"] = prior["registration_method"]
        else:
            payload.setdefault("registration_method", "dcr")
        secrets["dcr_credentials"] = payload
        source.secrets = secrets
        await self._repo.update(source)
