"""The per-agent self-configuration credential and its lookup source.

Leg 2 (`self-configuration-surface-read`), LD2 / DD2 / DD4.

Each enabled agent gets exactly one credential (`agt`-prefixed, same shape
as :class:`~the_one.api_credential.LocalApiCredential`), minted by
``manage.enable`` and stored ONLY inside the surface row's encrypted
``secrets["Authorization"]`` (never on ``AgentConfig`` — see the flight's
DD2). Resolution happens through an in-memory registry rather than a
per-request DB read, because the credential-gate's lookup seam
(``the_one.api_credential.resolve_caller``) is synchronous and walked on
every request.

The registry is the single source of truth for "which identifier maps to
which surface row, with which secret" for the lifetime of the process. It
is rebuilt from the DB at three points: process startup
(``manage.reconcile_on_startup``), enable, and disable/delete (via this
module's ``register`` / ``unregister``). A registry entry with no
corresponding live row (deleted out from under it, or the owner's
``mcp_source_ids`` no longer containing it) is caught by the surface's
DD9 refusal at tool-call time, not here — this module only answers
"does this token resolve to *some* registered identity."
"""

from __future__ import annotations

import hmac
from typing import Any, Iterable

from the_one.api_credential import IdentifiedCaller, LocalApiCredential
from the_one.db.models import MCPSource
from the_one.self_configuration.constants import (
    AGENT_CREDENTIAL_PREFIX,
    CREDENTIAL_SECRET_KEY,
    SOURCE_NAME,
    is_surface_row,
)

_BEARER_PREFIX = "Bearer "

# identifier -> (source_id, secret). Process-local, in-memory (Edge Case:
# "two processes sharing a data dir" is already unsupported per SECURITY-MODEL.md's
# "Single-process-at-a-time assumption"; this registry inherits that posture).
_registry: dict[str, tuple[str, str]] = {}

# NOTE: no boolean "already registered" flag here (there was one; removed).
# A flag survives independently of `api_credential._sources`'s actual
# contents, and that list is routinely swapped wholesale by test fixtures
# (`monkeypatch.setattr(api_credential, "_sources", [...])` —
# `tests/test_credential_gate.py`'s per-test isolation fixture does exactly
# this around every test, including ones that drive the real app's lifespan
# via `TestClient`). A flag left `True` after such a swap would report
# "already registered" while the actual list no longer contains this
# module's source — silently leaving the surface's credential source
# unregistered for the rest of the process. `register_credential_source_once`
# below checks ACTUAL LIST MEMBERSHIP instead, which self-heals across any
# number of such swaps.


def mint() -> LocalApiCredential:
    """Generate a fresh per-agent credential. Uses `secrets`, never `random`
    (delegates to :meth:`LocalApiCredential.generate`)."""
    return LocalApiCredential.generate()


def encode_for_header(credential: LocalApiCredential) -> str:
    """Return the ``Authorization: Bearer <token>`` header VALUE for
    *credential* — the exact string persisted at
    ``source.secrets[CREDENTIAL_SECRET_KEY]`` per DD2, so
    ``build_request_headers`` (``mcp/transports/streamable_http.py``) flat-
    merges it onto every outgoing request unchanged."""
    return f"{_BEARER_PREFIX}{credential.encode(prefix=AGENT_CREDENTIAL_PREFIX)}"


def credential_from_header(value: Any) -> LocalApiCredential | None:
    """Parse the ``Authorization: Bearer <token>`` header VALUE persisted at
    ``source.secrets[CREDENTIAL_SECRET_KEY]`` back into a
    :class:`LocalApiCredential`. Returns ``None`` on anything malformed
    (non-string, missing ``Bearer `` prefix, wrong credential prefix) —
    never raises. Public so both this module's :func:`load_from_rows` and
    ``manage``'s orphaned-row reuse path share one parse.
    """
    if not isinstance(value, str) or not value.startswith(_BEARER_PREFIX):
        return None
    return LocalApiCredential.parse(value[len(_BEARER_PREFIX) :], prefix=AGENT_CREDENTIAL_PREFIX)


def register(source_id: str, credential: LocalApiCredential) -> None:
    """Register *credential* as resolving to *source_id*. Overwrites any
    prior entry for the same identifier (re-enable after a stale registry
    entry, or startup reconcile re-registering an already-loaded row)."""
    _registry[credential.identifier] = (source_id, credential.secret)


def unregister(source_id: str) -> None:
    """Remove every registry entry whose ``source_id`` matches. Idempotent
    on no-match (disable/delete on an already-unregistered row)."""
    stale = [identifier for identifier, (sid, _) in _registry.items() if sid == source_id]
    for identifier in stale:
        del _registry[identifier]


def source_id_for(identifier: str) -> str | None:
    """Return the ``source_id`` registered for *identifier*, or ``None``."""
    entry = _registry.get(identifier)
    return entry[0] if entry is not None else None


def load_from_rows(sources: Iterable[MCPSource]) -> None:
    """Rebuild the registry from every marked (self-configuration) row's
    persisted credential. Clears any prior in-memory state first — this is
    the startup-reconcile / "registry and DB disagree" recovery path (leg
    Edge Cases): a credential for a row that no longer exists (or is no
    longer marked) simply stops resolving after this call.

    Rows are filtered by the ownership marker — ``constants.is_surface_row``
    (squawk 0004: previously duplicated inline here to avoid a circular
    import; both this module and ``manage`` now import the predicate from
    the leaf ``constants`` module instead).
    """
    _registry.clear()
    for source in sources:
        if source.type != "streamable-http":
            continue
        if not is_surface_row(source):
            continue
        header_value = (source.secrets or {}).get(CREDENTIAL_SECRET_KEY)
        credential = credential_from_header(header_value)
        if credential is None:
            continue
        register(source.id, credential)


def clear_for_test() -> None:
    """Wipe the registry. Test-only seam — mirrors the connector
    registry's now-deleted ``clear_for_test`` naming convention."""
    _registry.clear()


class SelfConfigurationCredentialSource:
    """Resolves an ``agt``-prefixed credential against the in-memory
    registry (DD2, LD2). Registered once against
    :func:`the_one.api_credential.register_source` — see
    :func:`register_credential_source_once`."""

    name = SOURCE_NAME

    def resolve(self, presented: str) -> IdentifiedCaller | None:
        parsed = LocalApiCredential.parse(presented, prefix=AGENT_CREDENTIAL_PREFIX)
        if parsed is None:
            return None
        entry = _registry.get(parsed.identifier)
        if entry is None:
            return None
        _source_id, secret = entry
        # Constant-time comparison — mirrors FileCredentialSource.resolve.
        if not hmac.compare_digest(parsed.secret, secret):
            return None
        return IdentifiedCaller(identifier=parsed.identifier, source=self.name)


def register_credential_source_once() -> None:
    """Register :class:`SelfConfigurationCredentialSource` against the
    shared lookup seam (``the_one.api_credential.register_source``) unless
    an instance is already present. Called from lifespan startup (explicit,
    testable — leg Implementation Guidance #1) rather than at package
    import time. Safe to call on every lifespan cycle — idempotent by
    ACTUAL LIST MEMBERSHIP (see the module comment above), not a flag, so
    it self-heals if something has swapped ``api_credential._sources`` out
    from under a prior registration.
    """
    from the_one import api_credential

    if any(
        isinstance(source, SelfConfigurationCredentialSource) for source in api_credential._sources
    ):
        return
    api_credential.register_source(SelfConfigurationCredentialSource())


def reset_registration_for_test() -> None:
    """Test-only no-op, kept as a stable call site for any test written
    against the old flag-based guard. Registration is now idempotent by
    list membership (see :func:`register_credential_source_once`), so
    there is no flag left to reset — this function exists only so such a
    call site does not need to be deleted.
    """
    return
