"""The external-client self-configuration credential and its lookup source.

M21 F03 L01 (`external-credential-grant`), DD1 / DD2 / DD8 / DD9.

Distinct from ``credentials.py``'s per-agent ``agt`` principal: each
operator grant mints a new ``ext``-prefixed credential (its own identifier
and secret) that resolves to exactly one agent's surface row but is tagged
``EXTERNAL_SOURCE_NAME`` — so it can be revoked or rotated independently of
the agent's own credential (DD1/DD7). Persisted (Fernet-encrypted) in
``agent_external_credentials`` (``AgentExternalCredentialRepository``);
resolution goes through this in-memory registry rather than a per-request
DB read, exactly as the ``agt`` path does, because the credential-gate's
lookup seam (``the_one.api_credential.resolve_caller``) is synchronous and
walked on every request.

The registry maps ``identifier -> (source_id, secret)``. It is rebuilt from
the store at process startup (the lifespan reconcile in
``interfaces/web/app.py`` calls :func:`load_from_rows` with
``AgentExternalCredentialRepository.load_all()``), mutated live on mint /
revoke / rotate (the operator endpoints in ``api.py``), and evicted on
surface teardown (``manage.disable`` / ``manage.cascade_delete``). A
registry entry whose surface row has since been disabled (deleted, or the
owner's ``mcp_source_ids`` no longer containing it) is caught by the
surface's DD9 refusal at tool-call time (``surface._calling_agent``), not
here — this module only answers "does this token resolve to *some*
registered identity."
"""

from __future__ import annotations

import hmac
from typing import Iterable

from the_one.api_credential import IdentifiedCaller, LocalApiCredential
from the_one.self_configuration.constants import (
    EXTERNAL_CREDENTIAL_PREFIX,
    EXTERNAL_SOURCE_NAME,
)

# identifier -> (source_id, secret). Process-local, in-memory — inherits the
# single-process assumption the `agt` registry documents (see
# ``credentials.py``).
_ext_registry: dict[str, tuple[str, str]] = {}

# NOTE: no boolean "already registered" flag here — the same reasoning as
# ``credentials.py``'s module comment applies verbatim. A flag survives
# independently of ``api_credential._sources``'s actual contents, which test
# fixtures routinely swap wholesale (``monkeypatch.setattr(api_credential,
# "_sources", [...])``); a stale ``True`` would silently leave this source
# unregistered for the rest of the process. :func:`register_credential_source_once`
# below checks ACTUAL LIST MEMBERSHIP instead, self-healing across any such
# swap.


def register(source_id: str, credential: LocalApiCredential) -> None:
    """Register *credential* as resolving to *source_id*. Overwrites any
    prior entry for the same identifier (rotate re-registering, or startup
    reconcile re-registering an already-loaded row)."""
    _ext_registry[credential.identifier] = (source_id, credential.secret)


def unregister(source_id: str) -> None:
    """Remove every registry entry whose ``source_id`` matches. Idempotent
    on no-match. This is the SURFACE-TEARDOWN eviction (disable /
    cascade_delete) — the FK cascade has already removed the store rows for
    the surface; this drops the in-memory entries. Mirrors
    ``credentials.unregister``."""
    stale = [identifier for identifier, (sid, _) in _ext_registry.items() if sid == source_id]
    for identifier in stale:
        del _ext_registry[identifier]


def unregister_identifier(identifier: str) -> None:
    """Remove a single credential's registry entry by *identifier*.
    Idempotent on no-match. This is the PER-PRINCIPAL eviction (revoke /
    rotate), distinct from :func:`unregister` which drops every entry for a
    whole surface."""
    _ext_registry.pop(identifier, None)


def source_id_for(identifier: str) -> str | None:
    """Return the ``source_id`` registered for *identifier*, or ``None``."""
    entry = _ext_registry.get(identifier)
    return entry[0] if entry is not None else None


def load_from_rows(rows: Iterable[tuple[str, str, str]]) -> None:
    """Rebuild the registry from ``(identifier, source_id, secret)`` tuples
    (``AgentExternalCredentialRepository.load_all()``). Clears any prior
    in-memory state first — the startup-reconcile / "registry and DB
    disagree" recovery path (DD8): a credential whose row is gone simply
    stops resolving after this call."""
    _ext_registry.clear()
    for identifier, source_id, secret in rows:
        _ext_registry[identifier] = (source_id, secret)


def clear_for_test() -> None:
    """Wipe the registry. Test-only seam — mirrors
    ``credentials.clear_for_test``."""
    _ext_registry.clear()


class ExternalAgentCredentialSource:
    """Resolves an ``ext``-prefixed credential against the in-memory
    external registry (DD1). Registered once against
    :func:`the_one.api_credential.register_source` — see
    :func:`register_credential_source_once`. Mirrors
    ``SelfConfigurationCredentialSource``."""

    name = EXTERNAL_SOURCE_NAME

    def resolve(self, presented: str) -> IdentifiedCaller | None:
        parsed = LocalApiCredential.parse(presented, prefix=EXTERNAL_CREDENTIAL_PREFIX)
        if parsed is None:
            return None
        entry = _ext_registry.get(parsed.identifier)
        if entry is None:
            return None
        _source_id, secret = entry
        # Constant-time comparison — mirrors FileCredentialSource.resolve.
        if not hmac.compare_digest(parsed.secret, secret):
            return None
        return IdentifiedCaller(identifier=parsed.identifier, source=self.name)


def register_credential_source_once() -> None:
    """Register :class:`ExternalAgentCredentialSource` against the shared
    lookup seam (``the_one.api_credential.register_source``) unless an
    instance is already present. Called from lifespan startup (explicit,
    testable) rather than at package import time. Safe to call on every
    lifespan cycle — idempotent by ACTUAL LIST MEMBERSHIP (see the module
    comment), not a flag, so it self-heals if something has swapped
    ``api_credential._sources`` out from under a prior registration.
    """
    from the_one import api_credential

    if any(
        isinstance(source, ExternalAgentCredentialSource) for source in api_credential._sources
    ):
        return
    api_credential.register_source(ExternalAgentCredentialSource())
