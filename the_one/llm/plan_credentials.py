"""Self-resolving credential source for ``anthropic-plan`` providers.

M19 F01 DD-3: a process-wide registry of per-provider-config credential
sources. Each source owns token reads and refreshes for one stored
``anthropic-plan`` provider row behind an asyncio lock:

- **Proactive refresh** — ``get_access_token()`` returns the stored token
  while it is comfortably fresh, and refreshes when ``token_expires_at``
  is within :data:`EXPIRY_MARGIN_SECONDS` (or missing — a token with no
  expiry is treated as expired rather than served possibly-dead).
- **Single-flight** — concurrent consumers serialize on the lock, so N
  callers racing an expired-token window produce exactly one refresh HTTP
  call; the waiters adopt the freshly stored token via the re-read rule.
- **Re-read-inside-lock adoption** — before refreshing, the source
  re-reads the stored secrets and ADOPTS a newer stored token instead of
  refreshing. This is the cheap insurance for the documented dev-instance
  + installed-app pattern (two processes sharing one SQLite file), where
  the asyncio lock alone cannot arbitrate. Single-process single-flight
  is guaranteed; cross-process safety is reduced-not-eliminated (explicit
  flight decision).
- **Rotation-safe write-back** — a successful refresh merges the new
  token set OVER the existing stored secrets (never a wholesale
  ``to_secrets()`` write, which omits ``None``-valued keys and would
  silently drop stored ``scope``/``token_type``/``token_expires_at``)
  and persists via ``LLMProviderRepository.update_secrets``.
- **Typed terminal failure** — a refresh rejected with an
  invalid-grant-style 4xx raises :class:`ReauthRequiredError` carrying
  the provider id. Stored secrets are NOT cleared (the operator may
  retry or re-authenticate; ``oauth_active`` semantics unchanged).
  Network errors re-raise as their existing typed OAuth errors —
  transient failures never demand re-auth.

Import discipline: anything that transitively reaches
``the_one.db.repositories`` is lazy-imported inside function bodies —
the circular-import convention documented in ``the_one/agent/factory.py``
(``agent.__init__`` → ``agent.factory`` → ``db.repositories`` →
``agent.config`` → ``agent.__init__``). Module level imports here must
stay DB-free so ``the_one.llm`` consumers can import this module freely.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

from the_one.llm import anthropic_oauth

if TYPE_CHECKING:
    from the_one.db.repositories import LLMProviderRepository

logger = logging.getLogger(__name__)

# Refresh proactively when the stored token expires within this window.
EXPIRY_MARGIN_SECONDS = 120

# A refresh response that omits ``expires_in`` gets this conservative
# short expiry rather than a never-expiring token (edge case: the next
# request window re-checks against a real deadline instead of serving a
# token of unknown lifetime forever).
FALLBACK_EXPIRES_IN_SECONDS = 300


class ReauthRequiredError(Exception):
    """Automatic token refresh can no longer succeed — the operator must
    re-authenticate the provider in Administration.

    Carries ``provider_id`` so API handlers and UI surfaces can key the
    re-auth affordance without message-parsing.
    """

    def __init__(self, provider_id: str, message: str | None = None):
        self.provider_id = provider_id
        super().__init__(
            message
            or (
                f"Anthropic plan provider '{provider_id}' requires re-authentication. "
                "Open the provider in Administration and sign in again."
            )
        )


async def _provider_repo() -> LLMProviderRepository:
    """Build a repository over the singleton connection + data-dir encryptor.

    Mirrors the construction at the existing call sites
    (``agent/factory.py``, web API). All imports are lazy — see the
    module docstring's circular-import note.
    """
    from the_one.config import settings
    from the_one.db.connection import get_connection
    from the_one.db.repositories import LLMProviderRepository
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    return LLMProviderRepository(conn, get_encryptor(settings.data_dir))


def _near_expiry(secrets: dict[str, Any], *, now: float | None = None) -> bool:
    """True when the stored token is within the refresh margin — or has no
    usable ``token_expires_at`` at all (missing/zero/garbage is treated as
    expired so a possibly-dead token is never served)."""
    expires_at = secrets.get("token_expires_at")
    if not isinstance(expires_at, (int, float)) or expires_at <= 0:
        return True
    return (now if now is not None else time.time()) >= expires_at - EXPIRY_MARGIN_SECONDS


class PlanCredentialSource:
    """Token reads + single-flight refresh for ONE provider-config row.

    Obtain instances via :func:`get_credential_source` — the process-wide
    registry keys one source (and one lock) per provider id, which is
    what makes the single-flight guarantee hold across every consumer
    (agents, connectors, ``/test``, ``/models``).
    """

    def __init__(self, provider_id: str):
        self.provider_id = provider_id
        self._lock = asyncio.Lock()
        # Test seam mirroring ``anthropic_oauth``'s injectable-client
        # convention: when set, refresh calls go through this client
        # (e.g. an ``httpx.MockTransport`` counting endpoint hits).
        self._http_client: httpx.AsyncClient | None = None

    async def _read(self) -> tuple[str, dict[str, Any]]:
        """Read the provider row; returns ``(display_name, secrets)``."""
        repo = await _provider_repo()
        provider = await repo.get(self.provider_id)
        return provider.name, dict(provider.secrets)

    async def get_access_token(self) -> str:
        """Return a fresh access token, refreshing (single-flight) if needed.

        Raises :class:`ReauthRequiredError` when no usable token set is
        stored or the refresh fails terminally;
        :class:`~the_one.llm.anthropic_oauth.OAuthExchangeError` on
        transient (network / 5xx) refresh failures.
        """
        name, secrets = await self._read()
        token = secrets.get("access_token")
        if token and not _near_expiry(secrets):
            return str(token)

        async with self._lock:
            # Re-read inside the lock: another consumer (or another
            # process sharing the SQLite file) may have refreshed while
            # we waited. Adopt a newer, still-fresh stored token instead
            # of refreshing again — this is what collapses N concurrent
            # callers into one refresh HTTP call.
            name, stored = await self._read()
            stored_token = stored.get("access_token")
            if stored_token and stored_token != token and not _near_expiry(stored):
                return str(stored_token)

            refresh = stored.get("refresh_token")
            if not refresh:
                raise ReauthRequiredError(
                    self.provider_id,
                    (
                        f"Anthropic plan provider '{name}' has no stored sign-in "
                        "credentials. Open the provider in Administration and "
                        "sign in with your Anthropic account."
                    ),
                )

            try:
                token_set = await anthropic_oauth.refresh_token(
                    str(refresh), client=self._http_client
                )
            except anthropic_oauth.OAuthExchangeError as exc:
                status = exc.status_code
                if status is not None and 400 <= status < 500:
                    # Invalid-grant-style rejection: the refresh token is
                    # expired/revoked. Terminal — surface the typed
                    # re-auth error. Stored secrets are deliberately NOT
                    # cleared (``oauth_active`` unchanged; the operator
                    # re-authenticates, or retries if the 4xx was a fluke).
                    raise ReauthRequiredError(
                        self.provider_id,
                        (
                            f"Anthropic plan provider '{name}' could not renew its "
                            f"credentials (token endpoint rejected the refresh, "
                            f"HTTP {status}). Re-authenticate the provider in "
                            "Administration."
                        ),
                    ) from exc
                # Network error / 5xx: transient — re-raise the existing
                # typed OAuth error; do not demand re-auth for a blip.
                raise

            # Merge the refreshed set OVER the existing stored secrets.
            # ``to_secrets()`` omits None-valued keys, so a response that
            # elides ``scope``/``token_type`` keeps the stored values, and
            # any non-managed keys survive untouched.
            merged = dict(stored)
            merged.update(token_set.to_secrets())
            if token_set.token_expires_at is None:
                # Response had no ``expires_in`` — store a conservative
                # short expiry rather than leaving a stale (or absent)
                # deadline that would either serve a dead token or force
                # refresh-every-request.
                merged["token_expires_at"] = int(time.time()) + FALLBACK_EXPIRES_IN_SECONDS

            repo = await _provider_repo()
            await repo.update_secrets(self.provider_id, merged)
            return token_set.access_token


# ── Process-wide registry ─────────────────────────────────────────────────

_sources: dict[str, PlanCredentialSource] = {}


def get_credential_source(provider_id: str) -> PlanCredentialSource:
    """Return the process-wide credential source for ``provider_id``.

    One source (and one lock) per provider id — every construction site
    (agent factory, connector inference, ``/test``, ``/models``) resolves
    through here so refreshes are single-flight process-wide.
    """
    source = _sources.get(provider_id)
    if source is None:
        source = PlanCredentialSource(provider_id)
        _sources[provider_id] = source
    return source


def evict_credential_source(provider_id: str) -> None:
    """Drop the cached source for ``provider_id`` (no-op when absent).

    Invalidation contract (DD-3): called on provider update (PUT), delete,
    OAuth reset, and after a fresh sign-in exchange — the next accessor
    call builds a fresh source that re-reads stored secrets.
    """
    _sources.pop(provider_id, None)


def _reset_for_tests() -> None:
    """Clear the registry (test isolation for the process-wide dict)."""
    _sources.clear()
