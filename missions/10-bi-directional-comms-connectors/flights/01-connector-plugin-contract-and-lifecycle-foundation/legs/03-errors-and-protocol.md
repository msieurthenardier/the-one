# Leg: errors-and-protocol

**Status**: landed
**Flight**: [Connector Plugin Contract and Lifecycle Foundation](../flight.md)

## Objective

Create the `the_one/connectors/` package (peer to `the_one/mcp/` and `the_one/tools/`) with two seed modules: `errors.py` (the 6-type typed exception hierarchy) and `base.py` (the 4-method `ConnectorPlugin` Protocol, the supporting `ConnectorClient` Protocol, and the four immutable dataclass types — `InboundEnvelope`, `OutboundTarget`, `DoctorReport`, `SessionKey`). Wire `__init__.py` so canonical-import paths are stable and re-exports work for convenience.

## Context

This is leg 3 of Flight 1 of Mission 10. Legs 1 + 2 landed the persistence floor (`connector_accounts` schema v13+v14, `ConnectorAccount` model, `ConnectorAccountRepository`, rotation transaction extended). This leg lands the **contract** that every subsequent leg of this flight and every subsequent flight of the mission codes against.

**Key design constraints from the flight that bind this leg**:

- **`ConnectorPlugin` Protocol has 4 methods** — not 6. Per flight Design Decisions: `connect`, `disconnect`, `doctor`, `normalize_session_key`. `AllowlistResolver` is a separate Protocol introduced by Flight 6; `CommandHandler` is a separate Protocol introduced by Flight 7. All three Protocols live in `connectors/base.py` — the "single contract file" mission criterion is about the file, not about the Protocol count.
- **`runtime_checkable` structural satisfaction**, no inheritance. Per `agents.md`'s `structural-Protocol-satisfaction` convention: classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. Mirrors `tools/provider.py:ToolProvider` and `agent/store.py:AgentConfigStore`.
- **6 typed exceptions**: `ConnectorClientError` (base) + `ConnectorConfigError` + `ConnectorConnectionError` + `ConnectorAuthRequired` + `ConnectorRegistrationError` + `ConnectorRateLimitError`. Mirrors the shape of `mcp/errors.py` (10 producer-side types in MCP; smaller upfront set for connectors with the explicit "grow deliberately when a real connector reveals a distinct error mode" stance).
- **`canonical-import + convenience-re-export`** discipline. The package's `__init__.py` re-exports for convenience, but code that touches Protocol identity (`isinstance(...)`, `try/except <ExceptionType>`) MUST use the canonical path `from the_one.connectors.base import ConnectorPlugin` and `from the_one.connectors.errors import <ExceptionType>`. Documented in the new `connectors/README.md` (leg 8's deliverable) AND noted in the `__init__.py` module docstring per the convention's reference in `agents.md`.

**`ConnectorClient` shape decision**: this leg ships `ConnectorClient` as a minimal Protocol with one method — `is_alive() -> bool`. The pool (legs 5+6) needs the liveness check for its reaper. Real connector clients (Discord client in Flight 8, Slack client in Flight 9) structurally satisfy this Protocol AND add their own platform-specific methods (e.g. a Discord client adds methods for posting messages, fetching channel info, etc.). The platform-send tool in Flight 4 will widen the `ConnectorClient` Protocol's contract additively when it needs outbound dispatch — this is the same widening-is-non-breaking-for-structural-Protocols pattern documented in `tools/provider.py:21-22`.

**Supporting type representation — `@dataclass(frozen=True, slots=True)`** for `InboundEnvelope`, `OutboundTarget`, `DoctorReport`, `SessionKey`. NOT Pydantic models, because these types are internal protocol-level message envelopes — they don't cross the JSON-schema-validated API boundary (where Pydantic earns its weight) and they benefit from immutability (frozen) and slot-defined memory layout (slots).

**Hashability — all four types are hashable**, but `InboundEnvelope.raw` and `DoctorReport.details` (both `dict[str, Any]`) are excluded from hash + equality via `field(hash=False, compare=False)`. Bare `frozen=True, slots=True` on a dataclass with a `dict` field constructs cleanly but raises `TypeError: unhashable type: 'dict'` at `hash()` time — caught during design review. The exclusion preserves hashability on the scalar fields while not pretending the dict contents are part of the type's identity. `SessionKey` and `OutboundTarget` have no dict fields, so they're hashable end-to-end and usable as dict keys (the agent-session mapping in Flight 3 of the mission keys on `SessionKey`).

## Inputs

What exists before this leg runs:

- Legs 1 + 2 landed (uncommitted on the `flight/01-connector-plugin-contract-and-lifecycle-foundation` branch)
- `the_one/db/_connector_types.py` exists with empty `CONNECTOR_TYPES: tuple[str, ...] = ()`
- `the_one/db/models.py` has `ConnectorAccount` with `id`, `name`, `type: str`, `config`, `secrets`, `created_at`, `updated_at`
- `the_one/db/repositories.py` has `ConnectorAccountRepository` with CRUD + encryption envelope
- Schema v14 includes the `name` column on `connector_accounts`
- The `the_one/connectors/` directory does NOT yet exist
- Patterns this leg mirrors:
  - `the_one/mcp/errors.py` (10-class hierarchy with `MCPClientError` base; narrow subclasses with single-sentence `__str__` for small-model consumption; `noqa: N818` comments where subclass names diverge from the conventional `Error` suffix — relevant for `ConnectorAuthRequired`)
  - `the_one/mcp/__init__.py` (re-export pattern with `noqa: E402` ordering; `__all__` declaration; module docstring)
  - `the_one/tools/provider.py:ToolProvider` (`@runtime_checkable` Protocol pattern — module docstring explaining structural-satisfaction, single-method shape, widening-is-non-breaking note)
  - `the_one/agent/store.py:AgentConfigStore` (second example of the runtime_checkable Protocol pattern in this codebase)
  - `agents.md` "structural-Protocol-satisfaction" convention at L42 and `canonical-import + convenience-re-export` convention at L36

## Outputs

What exists after this leg completes:

- New directory `the_one/connectors/`
- New file `the_one/connectors/__init__.py` — module docstring, canonical-import discipline note, re-exports of the public surface, `__all__` declaration
- New file `the_one/connectors/errors.py` — 6 typed exception classes
- New file `the_one/connectors/base.py` — `ConnectorPlugin` Protocol (4 methods), `ConnectorClient` Protocol (1 method), 4 frozen-slotted dataclass supporting types
- New file `tests/test_connectors.py` — test entrypoint for the connector subsystem
- Three test classes in `tests/test_connectors.py`:
  - `TestConnectorExceptions` — subclassing chain correct; each exception constructible with appropriate args; messages are single-sentence small-model-friendly
  - `TestConnectorPluginProtocol` — a minimal in-test class structurally satisfies `ConnectorPlugin`; widening (adding more methods to the test class) does not break the check; missing a method DOES break it
  - `TestConnectorClientProtocol` — analogous for `ConnectorClient`
  - `TestConnectorPackageExports` — canonical-import paths work (`from the_one.connectors.base import ConnectorPlugin`); convenience re-exports work (`from the_one.connectors import ConnectorPlugin`); both resolve to the same object
- `make test`, `make lint` clean
- Leg status `landed`
- Flight log gains a `### Leg 03: errors-and-protocol` entry

## Acceptance Criteria

- [ ] `the_one/connectors/` directory exists with three files: `__init__.py`, `errors.py`, `base.py`
- [ ] `the_one/connectors/errors.py` defines exactly 6 exception classes in this hierarchy:
    - `ConnectorClientError(Exception)` — base, no extra fields beyond `Exception`'s message
    - `ConnectorConfigError(ConnectorClientError)` — raised when an account's `config` or `secrets` dict is invalid (missing required field, malformed value)
    - `ConnectorConnectionError(ConnectorClientError)` — raised on transport / network / handshake failure
    - `ConnectorAuthRequired(ConnectorClientError)` — control-flow signal for re-authentication; carries `account_id` (always) and optional `account_name`, mirroring `MCPAuthRequired`'s shape; suffix-name `Required` not `Error` — add `noqa: N818` for the class (matching `MCPAuthRequired`'s pattern)
    - `ConnectorRegistrationError(ConnectorClientError)` — raised when a connector type cannot register (unknown type, collision in registry)
    - `ConnectorRateLimitError(ConnectorClientError)` — raised on platform rate-limit response; carries `retry_after_seconds: float | None`
- [ ] Each exception's `__init__` produces a single-sentence `__str__` suitable for the agent loop / tool-result strings (no nested causes, no rich tracebacks — match the `mcp/errors.py` convention noted in its module docstring)
- [ ] `the_one/connectors/base.py` defines:
    - `ConnectorPlugin` — `@runtime_checkable` Protocol with exactly 4 methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`) — signatures documented but bodies are `...`
    - `ConnectorClient` — `@runtime_checkable` Protocol with exactly 1 method (`is_alive() -> bool`); widening note in the docstring
    - `InboundEnvelope` — `@dataclass(frozen=True, slots=True)` carrying the inbound message metadata (platform, account_id, channel_id, thread_id, peer_id, peer_name, text, raw payload — see Implementation Guidance for exact fields). `raw` is annotated with `field(hash=False, compare=False)` so the envelope is hashable despite the dict field
    - `OutboundTarget` — `@dataclass(frozen=True, slots=True)` carrying the destination (channel_id, thread_id)
    - `DoctorReport` — `@dataclass(frozen=True, slots=True)` carrying probe result (status as `Literal["ok", "degraded", "failed"]`, message, details). `details` is annotated with `field(hash=False, compare=False)` so the report is hashable despite the dict field
    - `SessionKey` — `@dataclass(frozen=True, slots=True)` carrying the normalized session binding (platform, account_id, channel_id, thread_id, peer_id) — hashable for use as a dict key (no dict fields)
- [ ] `the_one/connectors/__init__.py` module docstring includes the canonical-import discipline note (verbatim or close to: "Code that touches Protocol identity or exception class identity MUST use canonical paths `from the_one.connectors.base import ...` and `from the_one.connectors.errors import ...`. The re-exports below are convenience only.")
- [ ] `the_one/connectors/__init__.py` re-exports the public surface and declares `__all__` listing every re-export
- [ ] `tests/test_connectors.py` exists with the four test classes named above, and all tests pass
- [ ] Convenience re-export resolves to the same class object as canonical import (i.e. `from the_one.connectors import ConnectorPlugin` is `from the_one.connectors.base import ConnectorPlugin` — `is` identity, not just `==` equality)
- [ ] A minimal in-test class satisfying `ConnectorPlugin` passes `isinstance(obj, ConnectorPlugin)` — and a class missing one of the 4 methods FAILS the check
- [ ] `ConnectorPlugin` and `ConnectorClient` implementations DO NOT inherit from the Protocols (structural satisfaction only)
- [ ] `hash(InboundEnvelope(...))` and `hash(DoctorReport(...))` succeed (do not raise `TypeError`); two envelopes/reports that differ only in their dict field have identical hashes and compare `==` (the dict is excluded from both hash and equality)
- [ ] A test documents that a sync `def connect(...)` falsely satisfies the `ConnectorPlugin` Protocol — known runtime_checkable limitation, surfaced in the suite so a future reader does not expect `isinstance` to catch async/sync mismatches
- [ ] `make test` clean; `make lint` clean
- [ ] Leg status `landed`
- [ ] `errors-and-protocol` checkbox checked in the flight artifact's Legs section
- [ ] Flight log has `### Leg 03: errors-and-protocol` entry under `## Leg Progress`

## Verification Steps

1. **Package layout**:
   - `docker exec the-one ls the_one/connectors/` returns exactly `__init__.py`, `base.py`, `errors.py` (in some order)

2. **Exception hierarchy**:
   - `docker exec the-one python -c "from the_one.connectors.errors import ConnectorClientError, ConnectorConfigError, ConnectorConnectionError, ConnectorAuthRequired, ConnectorRegistrationError, ConnectorRateLimitError; assert all(issubclass(c, ConnectorClientError) for c in [ConnectorConfigError, ConnectorConnectionError, ConnectorAuthRequired, ConnectorRegistrationError, ConnectorRateLimitError]); assert issubclass(ConnectorClientError, Exception); print('ok')"`

3. **Protocol structural satisfaction**:
   - `TestConnectorPluginProtocol` is the canonical verifier

4. **Canonical-import identity**:
   - `docker exec the-one python -c "from the_one.connectors import ConnectorPlugin as A; from the_one.connectors.base import ConnectorPlugin as B; assert A is B; print('ok')"`

5. **All exceptions constructible**:
   - `TestConnectorExceptions` is the canonical verifier; verify each exception with its required args (e.g. `ConnectorAuthRequired(account_id="a1")`) and check `str(exc)` is non-empty single-sentence shape

6. **No regression**:
   - `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_db_migration.py tests/test_db_repositories.py tests/test_provider_api.py tests/test_encryption.py tests/test_schema.py` clean
   - `docker exec the-one pytest -x --timeout 30` full suite clean
   - `make lint` clean

## Implementation Guidance

Execute in this order.

### Step 1: Create the package directory and `errors.py`

```bash
mkdir -p the_one/connectors/
```

Create `the_one/connectors/errors.py` modeled on `the_one/mcp/errors.py`. Match the module-docstring convention (explain the "single base class with narrow subclasses; single-sentence `__str__` for small-model consumption; no nested causes" stance).

```python
"""Connector client error hierarchy.

Single base class with narrow subclasses. Each subclass formats a clean
single-sentence ``__str__`` for small-model consumption — mirrors the
``the_one/mcp/errors.py`` shape. No nested causes, no rich tracebacks
visible in tool-result strings.

The connector hierarchy starts smaller than MCP's (6 producer-side types
vs MCP's 10). Subsequent flights MAY add types when a real platform
reveals a distinct error mode that doesn't fit any existing type —
deliberate growth, not speculative.
"""


class ConnectorClientError(Exception):
    """Base for all connector-client-raised errors."""


class ConnectorConfigError(ConnectorClientError):
    """An account's config or secrets dict is invalid — missing required
    field, malformed value, or otherwise rejected by the plugin's
    validation."""

    def __init__(self, account_id: str, validation_message: str) -> None:
        self.account_id = account_id
        self.validation_message = validation_message
        super().__init__(
            f"Connector account {account_id!r} config rejected: {validation_message}"
        )


class ConnectorConnectionError(ConnectorClientError):
    """Transport / network / handshake failure connecting to the platform."""


class ConnectorAuthRequired(ConnectorClientError):  # noqa: N818  (control-flow signal, not "Error" semantically; subclass of ConnectorClientError)
    """Raised when a connector operation requires user re-authentication.

    Control-flow signal — mirrors :class:`the_one.mcp.errors.MCPAuthRequired`.
    Carries ``account_id`` (always) and optional ``account_name`` for
    operator-facing surfaces.
    """

    def __init__(
        self,
        account_id: str,
        *,
        account_name: str | None = None,
    ) -> None:
        super().__init__(f"Authorization required for connector account {account_id}")
        self.account_id = account_id
        self.account_name = account_name


class ConnectorRegistrationError(ConnectorClientError):
    """Raised when a connector type cannot register cleanly.

    Two failure modes covered: (a) unknown type passed to the registry;
    (b) collision in the registry (two plugins registered under the same
    type name).
    """

    def __init__(self, type_name: str, reason: str) -> None:
        self.type_name = type_name
        self.reason = reason
        super().__init__(f"Connector type {type_name!r} registration failed: {reason}")


class ConnectorRateLimitError(ConnectorClientError):
    """Raised when the platform returns a rate-limit response.

    Carries ``retry_after_seconds`` when the platform advertises one
    (Discord ``X-RateLimit-Reset-After``, Slack ``Retry-After``); ``None``
    when no hint is given.
    """

    def __init__(
        self,
        account_id: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.account_id = account_id
        self.retry_after_seconds = retry_after_seconds
        if retry_after_seconds is not None:
            msg = (
                f"Connector account {account_id!r} rate-limited; "
                f"retry after {retry_after_seconds:.1f}s"
            )
        else:
            msg = f"Connector account {account_id!r} rate-limited (no retry hint)"
        super().__init__(msg)
```

### Step 2: Create `the_one/connectors/base.py`

```python
"""Connector plugin contract.

The single file every future connector author opens to implement support
for a new third-party communication platform. The four-method
:class:`ConnectorPlugin` Protocol below is the type-level adapter contract;
:class:`ConnectorClient` is the per-instance live-connection wrapper that
each plugin's :meth:`connect` returns.

Per ``agents.md`` ``structural-Protocol-satisfaction``: implementations
satisfy the Protocols structurally and DO NOT inherit from them. A connector
that supports allowlists and platform-side commands additionally satisfies
the :class:`AllowlistResolver` and :class:`CommandHandler` Protocols
(introduced by flights 6 and 7 of mission 10). All three Protocols will live
in this file — "single contract file" is the mission criterion, not "single
Protocol".

Per ``agents.md`` ``canonical-import + convenience-re-export``: code that
touches Protocol identity (``isinstance(...)`` or subclass checks) MUST use
the canonical import path from this module, not from ``the_one.connectors``
(the package-level ``__init__.py`` re-exports for convenience only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from the_one.db.models import ConnectorAccount
from the_one.encryption import Encryptor


@dataclass(frozen=True, slots=True)
class InboundEnvelope:
    """A message received from the external platform, normalized for routing.

    The plugin's gateway-listener / webhook-receiver constructs one of
    these per inbound message and hands it to the connector subsystem.
    """

    platform: str
    """The connector's ``type`` value (e.g. ``"discord"``, ``"slack"``)."""

    account_id: str
    """The :class:`ConnectorAccount.id` whose gateway delivered this message."""

    channel_id: str
    """Platform-native channel identifier (Discord channel snowflake, Slack
    channel id). For DMs, this is the DM channel; for guild messages, the
    text channel."""

    thread_id: str | None
    """Platform-native thread identifier when the message is in a thread;
    ``None`` for top-level channel messages."""

    peer_id: str
    """Platform-native peer identifier (the sender's Discord user id, Slack
    user id, etc.)."""

    peer_name: str
    """The sender's display name on the platform at the moment of inbound."""

    text: str
    """The message body as plain text (platform-specific markup stripped)."""

    raw: dict[str, Any] = field(hash=False, compare=False)
    """The platform-native payload, untransformed. Plugins may consult this
    for fields not yet promoted to first-class envelope attributes
    (attachments, embeds, etc.).

    Required at construction time. Excluded from ``__hash__`` and ``__eq__``
    via ``field(hash=False, compare=False)`` — bare ``frozen=True, slots=True``
    on a dataclass with a ``dict`` field constructs fine but ``hash()`` raises
    ``TypeError: unhashable type: 'dict'``. Hashability is preserved on the
    scalar fields; dict contents are not part of the envelope's identity.
    """


@dataclass(frozen=True, slots=True)
class OutboundTarget:
    """Where on the platform an agent's reply is being sent."""

    channel_id: str
    """The platform-native channel id to deliver the message to."""

    thread_id: str | None = None
    """Optional thread to post into; ``None`` posts in the channel itself."""


@dataclass(frozen=True, slots=True)
class SessionKey:
    """Normalized binding between an external conversation and an internal
    ``chat_sessions`` row.

    Built by :meth:`ConnectorPlugin.normalize_session_key`. Hashable
    (``frozen=True``, ``slots=True``) so it can be used as a dict key in
    the agent-session mapping that flight 3 of mission 10 introduces.

    The exact set of fields that participate in the key (e.g. does
    ``thread_id`` separate the binding or fold into the channel?) is a
    flight-3 design decision. This dataclass carries all candidate fields;
    flight 3's normalization logic decides which to populate.
    """

    platform: str
    account_id: str
    channel_id: str
    thread_id: str | None = None
    peer_id: str | None = None


@dataclass(frozen=True, slots=True)
class DoctorReport:
    """Result of a :meth:`ConnectorPlugin.doctor` probe.

    Mirrors the diagnostic shape M07's MCP inspector established (status
    plus a human-readable message plus optional structured details for the
    admin UI).
    """

    status: Literal["ok", "degraded", "failed"]
    """The probe outcome — ``ok`` if every check passed, ``degraded`` if the
    connection works but a non-critical check failed, ``failed`` if the
    plugin cannot use this account."""

    message: str
    """One-sentence human-readable summary suitable for the admin UI's
    inline status. Mirrors the small-model-friendly convention of
    ``the_one/mcp/errors.py``."""

    details: dict[str, Any] = field(hash=False, compare=False)
    """Required structured detail surface for the admin UI's expanded
    probe view. Plugins MAY pass an empty dict when there is nothing
    platform-specific to surface. Plugins MAY populate platform-specific
    fields (token fingerprint, intent coverage, gateway endpoint, etc.).
    The shape is not standardized across plugins.

    Excluded from ``__hash__`` and ``__eq__`` — same rationale as
    :attr:`InboundEnvelope.raw`.
    """


@runtime_checkable
class ConnectorClient(Protocol):
    """Live-connection wrapper for a single connector account.

    Each :meth:`ConnectorPlugin.connect` invocation produces a
    :class:`ConnectorClient`. The per-(agent, account) lifecycle pool
    (legs 5+6 of this flight) holds one client per warm entry and calls
    :meth:`is_alive` to decide whether the client needs respawn.

    ``runtime_checkable`` Protocol checks method NAMES only, so widening
    this surface is non-breaking for any existing
    ``isinstance(client, ConnectorClient)`` check. Flight 4 widens this
    to add an outbound-send method when the platform-send tool needs it.
    """

    def is_alive(self) -> bool:
        """Return ``True`` if the underlying platform connection is healthy.

        Called periodically by the lifecycle pool's reaper. ``False``
        triggers an evict-and-respawn; a raised exception is treated as
        ``False`` plus logged.
        """
        ...


@runtime_checkable
class ConnectorPlugin(Protocol):
    """Type-level adapter for a third-party communication platform.

    Implementations (one per platform — ``DiscordPlugin``, ``SlackPlugin``,
    ``StubPlugin``) structurally satisfy this Protocol WITHOUT inheriting
    from it. Each plugin is stateless at the type level — per-account
    state lives on the :class:`ConnectorClient` instances returned by
    :meth:`connect`.

    ``runtime_checkable`` Protocol checks method NAMES only. Widening this
    Protocol is non-breaking for existing
    ``isinstance(plugin, ConnectorPlugin)`` consumers, so subsequent flights
    can add methods deliberately. Flights 6 and 7 do NOT widen this Protocol
    — they introduce separate :class:`AllowlistResolver` and
    :class:`CommandHandler` Protocols, also in this file, that connectors
    structurally satisfy in addition to :class:`ConnectorPlugin`.
    """

    async def connect(
        self,
        account: ConnectorAccount,
        encryptor: Encryptor,
    ) -> ConnectorClient:
        """Open a live platform connection for ``account`` and return the client.

        ``encryptor`` is the system-wide :class:`Encryptor` instance used
        to decrypt ``account.secrets`` at call time. The plugin MUST NOT
        retain a reference to the decrypted plaintext past the call; the
        ``encryptor`` reference may be retained (rotation propagates
        through it).

        Raises :class:`ConnectorConfigError` if the account's config or
        secrets are invalid for this plugin; :class:`ConnectorConnectionError`
        if the platform is unreachable; :class:`ConnectorAuthRequired` if
        the platform reports that the operator needs to re-authenticate
        before connection can proceed.
        """
        ...

    async def disconnect(self, client: ConnectorClient) -> None:
        """Cleanly tear down ``client``'s platform connection.

        Called by the lifecycle pool at evict time and at shutdown drain.
        Should be best-effort idempotent — calling ``disconnect`` on a
        client that is already disconnected MUST NOT raise.
        """
        ...

    async def doctor(
        self,
        account: ConnectorAccount,
        encryptor: Encryptor,
    ) -> DoctorReport:
        """Probe ``account`` without dispatching messages to peers.

        Verifies the connection lifecycle, token validity, and any
        plugin-specific capability/permission preconditions. Returns a
        :class:`DoctorReport` rather than raising — failure is a normal
        outcome the admin UI renders, not an exception that crashes the
        request.
        """
        ...

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        """Compute the canonical :class:`SessionKey` for ``inbound``.

        The plugin decides which fields of the inbound envelope participate
        in the key (does ``thread_id`` separate the binding or fold into
        the channel? does the peer participate in a DM-only context?). The
        connector subsystem treats the returned key as opaque and uses it
        as a dict-lookup primitive against the agent-session mapping in
        flight 3 of mission 10.
        """
        ...
```

### Step 3: Create `the_one/connectors/__init__.py`

```python
"""Connector subsystem — bi-directional third-party communication platforms.

This package is a peer to :mod:`the_one.mcp` and :mod:`the_one.tools`. Flight 1
of mission 10 ships the contract and lifecycle plumbing here; flights 2-10
add the operator surfaces, the platform-send built-in tool, the routing and
command primitives, and the first two real connectors (Discord + one other).

**Canonical-import discipline** (``agents.md`` :: ``canonical-import +
convenience-re-export``): code that touches Protocol identity
(``isinstance(...)`` checks) or exception class identity (``try/except`` and
subclass checks) MUST use the canonical import paths:

- ``from the_one.connectors.base import ConnectorPlugin``,
  ``from the_one.connectors.base import ConnectorClient``
- ``from the_one.connectors.errors import ConnectorClientError`` (and
  subclasses)

The re-exports below are convenience only — they are NOT to be used in
``isinstance`` or exception-handler positions. A future package-internal
refactor could change what ``the_one.connectors.X`` resolves to without
violating any contract, but the canonical paths above are stable.
"""

from the_one.connectors.base import (
    ConnectorClient,
    ConnectorPlugin,
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
    SessionKey,
)
from the_one.connectors.errors import (
    ConnectorAuthRequired,
    ConnectorClientError,
    ConnectorConfigError,
    ConnectorConnectionError,
    ConnectorRateLimitError,
    ConnectorRegistrationError,
)

__all__ = [
    # Protocols + supporting types
    "ConnectorClient",
    "ConnectorPlugin",
    "DoctorReport",
    "InboundEnvelope",
    "OutboundTarget",
    "SessionKey",
    # Exception hierarchy
    "ConnectorAuthRequired",
    "ConnectorClientError",
    "ConnectorConfigError",
    "ConnectorConnectionError",
    "ConnectorRateLimitError",
    "ConnectorRegistrationError",
]
```

### Step 4: Create `tests/test_connectors.py`

```python
"""Tests for the connector subsystem foundation (mission 10 flight 01)."""

from __future__ import annotations

import dataclasses

import pytest

from the_one.connectors import (
    ConnectorAuthRequired,
    ConnectorClient,
    ConnectorClientError,
    ConnectorConfigError,
    ConnectorConnectionError,
    ConnectorPlugin,
    ConnectorRateLimitError,
    ConnectorRegistrationError,
    DoctorReport,
    InboundEnvelope,
    OutboundTarget,
    SessionKey,
)


class TestConnectorExceptions:
    """The 6-type exception hierarchy."""

    def test_subclassing_chain(self) -> None:
        """Every leaf inherits from ConnectorClientError, which inherits from Exception."""
        for cls in (
            ConnectorConfigError,
            ConnectorConnectionError,
            ConnectorAuthRequired,
            ConnectorRegistrationError,
            ConnectorRateLimitError,
        ):
            assert issubclass(cls, ConnectorClientError), cls
        assert issubclass(ConnectorClientError, Exception)

    def test_config_error_message(self) -> None:
        exc = ConnectorConfigError(account_id="a1", validation_message="missing BOT_TOKEN")
        assert "a1" in str(exc)
        assert "missing BOT_TOKEN" in str(exc)
        # single-sentence: no newlines
        assert "\n" not in str(exc)

    def test_connection_error_constructible_plain(self) -> None:
        exc = ConnectorConnectionError("gateway timeout")
        assert "gateway timeout" in str(exc)

    def test_auth_required_carries_account_id(self) -> None:
        exc = ConnectorAuthRequired(account_id="a1", account_name="My Bot")
        assert exc.account_id == "a1"
        assert exc.account_name == "My Bot"
        assert "a1" in str(exc)

    def test_auth_required_account_name_optional(self) -> None:
        exc = ConnectorAuthRequired(account_id="a1")
        assert exc.account_name is None

    def test_registration_error(self) -> None:
        exc = ConnectorRegistrationError(type_name="discord", reason="already registered")
        assert "discord" in str(exc)
        assert "already registered" in str(exc)

    def test_rate_limit_with_retry_hint(self) -> None:
        exc = ConnectorRateLimitError(account_id="a1", retry_after_seconds=12.5)
        assert exc.retry_after_seconds == 12.5
        assert "12.5" in str(exc)

    def test_rate_limit_no_retry_hint(self) -> None:
        exc = ConnectorRateLimitError(account_id="a1")
        assert exc.retry_after_seconds is None
        assert "no retry hint" in str(exc)


class _MinimalPlugin:
    """In-test class that structurally satisfies :class:`ConnectorPlugin`.

    NO inheritance — structural satisfaction per agents.md convention.
    """

    async def connect(self, account, encryptor):  # noqa: ANN001  (test stub)
        return _MinimalClient()

    async def disconnect(self, client):  # noqa: ANN001
        return None

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="stub", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
        )


class _MinimalClient:
    """In-test class that structurally satisfies :class:`ConnectorClient`."""

    def is_alive(self) -> bool:
        return True


class _PluginMissingConnect:
    """Plugin stub missing the ``connect`` method — must FAIL isinstance check."""

    async def disconnect(self, client):  # noqa: ANN001
        return None

    async def doctor(self, account, encryptor):  # noqa: ANN001
        return DoctorReport(status="ok", message="x", details={})

    def normalize_session_key(self, inbound):  # noqa: ANN001
        return SessionKey(platform="x", account_id="x", channel_id="x")


class TestConnectorPluginProtocol:
    def test_minimal_plugin_satisfies_protocol(self) -> None:
        assert isinstance(_MinimalPlugin(), ConnectorPlugin)

    def test_plugin_missing_method_fails_check(self) -> None:
        assert not isinstance(_PluginMissingConnect(), ConnectorPlugin)

    def test_plugin_does_not_inherit_from_protocol(self) -> None:
        """Structural satisfaction means no inheritance."""
        assert ConnectorPlugin not in _MinimalPlugin.__mro__


class TestConnectorClientProtocol:
    def test_minimal_client_satisfies_protocol(self) -> None:
        assert isinstance(_MinimalClient(), ConnectorClient)

    def test_client_missing_is_alive_fails_check(self) -> None:
        class _NoMethod:
            pass

        assert not isinstance(_NoMethod(), ConnectorClient)


class TestConnectorPackageExports:
    def test_canonical_and_re_exports_resolve_to_same_object(self) -> None:
        """Convenience re-export is `is`-identical to the canonical import."""
        from the_one.connectors import ConnectorPlugin as via_package
        from the_one.connectors.base import ConnectorPlugin as via_canonical

        assert via_package is via_canonical

        from the_one.connectors import ConnectorClientError as exc_via_package
        from the_one.connectors.errors import ConnectorClientError as exc_via_canonical

        assert exc_via_package is exc_via_canonical

    def test_supporting_types_round_trip(self) -> None:
        """Dataclass types are constructible and frozen."""
        env = InboundEnvelope(
            platform="stub",
            account_id="a1",
            channel_id="c1",
            thread_id=None,
            peer_id="p1",
            peer_name="Peer One",
            text="hi",
            raw={},
        )
        # Frozen — assignment must raise FrozenInstanceError specifically.
        with pytest.raises(dataclasses.FrozenInstanceError):
            env.text = "edited"  # type: ignore[misc]

        target = OutboundTarget(channel_id="c1")
        assert target.thread_id is None

        key = SessionKey(platform="stub", account_id="a1", channel_id="c1")
        # Hashable — usable as dict key.
        d = {key: "value"}
        assert d[SessionKey(platform="stub", account_id="a1", channel_id="c1")] == "value"

        rpt = DoctorReport(status="ok", message="ok", details={})
        assert rpt.status == "ok"

    def test_inbound_envelope_is_hashable_despite_dict_field(self) -> None:
        """InboundEnvelope.raw is excluded from hash via field(hash=False, compare=False)
        so the envelope is hashable on its scalar fields. Bare frozen+slots
        with a dict field constructs but blows up on hash() — locked here."""
        env = InboundEnvelope(
            platform="stub",
            account_id="a1",
            channel_id="c1",
            thread_id=None,
            peer_id="p1",
            peer_name="Peer One",
            text="hi",
            raw={"large": "payload"},
        )
        # Must not raise.
        h = hash(env)
        # Two envelopes that differ only in raw payload share the same hash
        # because raw is excluded from compare/hash.
        env2 = InboundEnvelope(
            platform="stub",
            account_id="a1",
            channel_id="c1",
            thread_id=None,
            peer_id="p1",
            peer_name="Peer One",
            text="hi",
            raw={"different": "payload"},
        )
        assert hash(env2) == h
        assert env == env2  # compare=False on raw means raw doesn't participate in __eq__

    def test_doctor_report_is_hashable_despite_dict_field(self) -> None:
        """DoctorReport.details is excluded from hash + eq — same contract
        as InboundEnvelope.raw."""
        rpt = DoctorReport(status="ok", message="connected", details={"token": "***"})
        h = hash(rpt)
        rpt2 = DoctorReport(status="ok", message="connected", details={"different": "x"})
        assert hash(rpt2) == h
        assert rpt == rpt2

    def test_sync_method_falsely_satisfies_async_protocol(self) -> None:
        """Document a known runtime_checkable limitation: ``isinstance(obj,
        ConnectorPlugin)`` checks method NAMES only — a class with a sync
        ``def connect(...)`` (non-async) falsely passes the check. Real
        type errors surface at call time when ``await plugin.connect(...)``
        rejects a non-coroutine return. This test exists to make the
        known-limitation visible in the test suite so a future reader
        understands isinstance is necessary-but-not-sufficient."""

        class _SyncConnectStub:
            def connect(self, account, encryptor):  # NOTE: sync, not async
                return _MinimalClient()

            async def disconnect(self, client):
                return None

            async def doctor(self, account, encryptor):
                return DoctorReport(status="ok", message="x", details={})

            def normalize_session_key(self, inbound):
                return SessionKey(
                    platform=inbound.platform,
                    account_id=inbound.account_id,
                    channel_id=inbound.channel_id,
                )

        # Falsely passes — documenting the limitation, not endorsing it.
        assert isinstance(_SyncConnectStub(), ConnectorPlugin)
```

### Step 5: Update flight artifacts + leg status

- Append a `### Leg 03: errors-and-protocol` entry under `## Leg Progress` in the flight log
- Check off `errors-and-protocol` in the flight's Legs section
- Set this leg's status to `landed`
- Signal `[HANDOFF:review-needed]`; do NOT commit

### Step 6: Run the targeted tests + full suite + lint

```bash
docker exec the-one pytest -x --timeout 30 tests/test_connectors.py
docker exec the-one pytest -x --timeout 30
docker exec the-one bash -c "cd /workspace && make lint"
```

## Edge Cases

- **`runtime_checkable` Protocols check names, not signatures.** A test class with a method named `connect` that takes a wrong number of arguments would still pass `isinstance` (per `tools/provider.py:19-22`'s note). This is a known trade-off of the structural-satisfaction approach. Real type errors surface at call time. No mitigation needed in this leg; downstream legs / flights consume the plugin and surface signature mismatches naturally.
- **`from __future__ import annotations` in `base.py`** — required because the Protocol method signatures reference `ConnectorClient` (defined later in the file) and `ConnectorAccount` (cross-module import). Without `__future__ annotations`, `ConnectorPlugin.connect`'s `-> ConnectorClient` annotation would NameError at module load time. Match the `tools/provider.py:1` pattern (`from __future__ import annotations`).
- **`frozen=True, slots=True` Python compatibility.** `slots=True` on `@dataclass` requires Python 3.10+. CLAUDE.md says the project supports 3.11+ (verified in pyproject.toml). Safe.
- **Pyflakes / ruff F401 on `__init__.py` re-exports.** The re-exports are intentional (public API). The `__all__` declaration silences F401 for these symbols. If ruff still complains, add `# noqa: F401` per-import or per-file — but prefer the `__all__` solution because it's documented project-wide convention.
- **`Literal["ok", "degraded", "failed"]` on `DoctorReport.status`.** Pydantic / static type checkers handle this fine on a dataclass field (no `Literal[*tuple]` unpacking trap from the `_provider_types.py` precedent — this is a literal-literal, not a tuple-derived one).
- **Empty test file pre-leg.** `tests/test_connectors.py` does not exist before this leg. Creating it from scratch (not appending to an existing file) avoids any import-ordering concerns.

## Files Affected

- `the_one/connectors/__init__.py` (NEW) — package entry, re-exports, canonical-import discipline note
- `the_one/connectors/errors.py` (NEW) — 6 typed exception classes
- `the_one/connectors/base.py` (NEW) — `ConnectorPlugin` + `ConnectorClient` Protocols + 4 dataclass supporting types
- `tests/test_connectors.py` (NEW) — 4 test classes covering exceptions, both Protocols, package exports
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — `errors-and-protocol` Legs-section checkbox checked
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight-log.md` — `### Leg 03: errors-and-protocol` entry under `## Leg Progress`
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/legs/03-errors-and-protocol.md` (this file) — status to `landed`

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All listed tests passing (`docker exec the-one pytest -x --timeout 30`)
- [ ] `make lint` clean
- [ ] Flight log updated with `### Leg 03` entry
- [ ] Leg status set to `landed` (NOT `completed`)
- [ ] `errors-and-protocol` checkbox checked in flight.md
- [ ] Signal `[HANDOFF:review-needed]`
- [ ] Do NOT commit — defer to flight-end

---

## Citation Audit

8 citations verified against current code at leg design time:

| Citation | Verification |
|---|---|
| `the_one/mcp/errors.py` (10-class hierarchy) | OK — read in full |
| `the_one/mcp/__init__.py` (re-export pattern, `noqa: E402` ordering, `__all__`) | OK — read in full |
| `the_one/tools/provider.py:ToolProvider` (`@runtime_checkable` Protocol pattern) | OK — read in full |
| `the_one/agent/store.py:AgentConfigStore` (second Protocol example) | OK — verified existence |
| `the_one/tools/builtins.py:BuiltinToolProvider` (structural-satisfaction implementer of ToolProvider) | OK — verified at line 60 |
| `the_one/db/models.py:ConnectorAccount` (post-leg-2) | OK — landed in leg 2 |
| `the_one/encryption.py:Encryptor` | OK — referenced by `ConnectorPlugin.connect`'s signature |
| `agents.md` :: `structural-Protocol-satisfaction` (L42) + `canonical-import + convenience-re-export` (L36) | OK — both conventions named in the leg's design constraints |
