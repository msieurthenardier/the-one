# Connector runtime invariants

This document is the package-level entry point for `the_one/connectors/`. It
captures the runtime invariants Mission 10 Flight 1 establishes — the
connector plugin contract, the per-(agent, account) lifecycle pool, the type
registry, and the encryption envelope. Read this BEFORE modifying anything in
the package — many of the invariants below are load-bearing for the test
suite AND for the operator's mental model of how connectors connect,
dispatch inbound, and reap.

For project-wide conventions (`trust-the-runtime`,
`canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`,
`verbatim-message-equality`, `container-test-entrypoints-reach-via-make`),
see `the_one/agents.md`'s "Project Conventions" section.

For the connector-type extension checklist and the full connector subsystem
decisions / invariants / known issues, see `the_one/agents.md`'s
"Connector type extension checklist" and "Connector subsystem" sections —
those are the canonical references; this README is the package-level
orientation pointer.

## §1. Package layout

```
the_one/connectors/
├── __init__.py        # Public surface re-exports; canonical-import discipline note
├── base.py            # ConnectorPlugin + ConnectorClient Protocols; supporting
│                      # dataclasses (InboundEnvelope, OutboundTarget, SessionKey,
│                      # DoctorReport). Future home of AllowlistResolver (Flight 6)
│                      # and CommandHandler (Flight 7).
├── errors.py          # 6-type exception hierarchy
├── registry.py        # ConnectorRegistry class + module-level singleton + builtin
│                      # discovery hook
├── _pool.py           # per-(agent, account) lifecycle pool (private)
└── _stub.py           # In-process test fixture (private; never registered in
                       # production discovery)
```

Per `canonical-import + convenience-re-export`: `__init__.py` re-exports the
public Protocols, supporting types, exception classes, and `ConnectorRegistry`
for convenience. Code that touches Protocol identity (`isinstance(...)`) or
exception class identity (`try/except` and subclass checks) MUST use the
canonical import paths (`the_one.connectors.base`, `the_one.connectors.errors`),
not the convenience re-exports.

## §2. Public API entry points

Production code interacts with the pool via two functions in
`the_one.connectors._pool`:

- `acquire(agent_name, account_id) -> ConnectorClient` — look up or spawn
  the warm client for `(agent, account)`. Cycle-2 race-safe; concurrent
  same-key acquires share one worker (the lock-held branch creates the
  entry on the first caller; subsequent callers wait on
  `entry.client_ready` outside the lock). Touches `entry.last_activity` on
  every successful resolve.
- `shutdown_drain() -> None` — cancel the reaper task and drain every
  warm entry. Wired into `interfaces/web/app.py:lifespan` AFTER the MCP
  pool drain and BEFORE the OAuth periodic-sweep stop. Bounded at ~10s
  total regardless of pool size (each `_evict` has a 10s per-entry
  timeout; evicts run in parallel via `asyncio.gather`).

Both are at `the_one.connectors._pool` rather than re-exported from
`__init__.py` — the pool module is package-private in Flight 1. Higher-level
entry points (e.g. a connector-side analog of `mcp.shutdown_drain`) may be
re-exported from `__init__.py` by future flights when there is a stable
operator-facing surface to bind to.

## §3. Protocol decomposition

`base.py` houses **multiple Protocols** — Flight 1 ships two, Flights 6 and 7
will add two more:

- `ConnectorPlugin` (Flight 1) — `connect`, `disconnect`, `doctor`,
  `normalize_session_key` (4 methods). The type-level adapter contract;
  every plugin class structurally satisfies this Protocol.
- `ConnectorClient` (Flight 1) — `is_alive` (1 method). The per-instance
  live-connection wrapper returned by `ConnectorPlugin.connect`.
- `AllowlistResolver` (Flight 6) — ACL-aware connectors will additionally
  satisfy this Protocol.
- `CommandHandler` (Flight 7) — connectors that handle platform-side
  commands (`/agents`, `/talk-to`, etc.) will additionally satisfy this
  Protocol.

Per the `structural-Protocol-satisfaction` convention, real connectors
(Discord — Flight 8; the second connector — Flight 9) do NOT inherit from
the Protocols. They simply expose methods with the right names + signatures
and the runtime-checkable Protocols accept them. Each Protocol a connector
claims to satisfy is asserted via `isinstance(conn, ProtocolType)` in the
per-platform integration tests — structural satisfaction is per-Protocol,
not subsystem-wide.

"Single contract file" (the mission criterion) means one `base.py`, not one
Protocol. Multiple Protocols in one file satisfy the criterion.

### Skeleton for a real plugin

Reference shape for Flight 8 (Discord) and Flight 9 (the second connector).
The platform is intentionally hypothetical — Discord and Slack ergonomics are
out of scope for this skeleton.

```python
# Registered via register_builtin_connectors() in connectors/registry.py —
# see agents.md "Connector type extension checklist".
from typing import Any

from the_one.connectors.base import (
    ConnectorClient,
    DoctorReport,
    InboundEnvelope,
    SessionKey,
)
from the_one.db.models import ConnectorAccount
from the_one.encryption import Encryptor


class HypotheticalPlatformPlugin:
    """Structural ConnectorPlugin — no inheritance per `structural-Protocol-satisfaction`."""

    async def connect(
        self, account: ConnectorAccount, encryptor: Encryptor
    ) -> ConnectorClient:
        secrets = account.secrets  # already-decrypted dict from the repository
        token = secrets["bot_token"]
        # pseudo-code — replace with real SDK call:
        platform_client: Any = await _open_platform_session(token)
        return platform_client  # must structurally satisfy ConnectorClient

    async def disconnect(self, client: ConnectorClient) -> None:
        # pseudo-code — idempotent close; do not raise if already closed
        await _close_platform_session(client)

    async def doctor(
        self, account: ConnectorAccount, encryptor: Encryptor
    ) -> DoctorReport:
        try:
            client = await self.connect(account, encryptor)
        except Exception as e:  # noqa: BLE001 — doctor surfaces failure, not raises
            return DoctorReport(status="error", details={"error": str(e)})
        try:
            # pseudo-code — minimal handshake probe; no message dispatch to peers
            info = await _platform_self_check(client)
            return DoctorReport(status="ok", details={"identity": info["bot_user"]})
        finally:
            await self.disconnect(client)

    def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
        # Plugin owns which envelope fields participate in the binding.
        return SessionKey(
            platform=inbound.platform,
            account_id=inbound.account_id,
            channel_id=inbound.channel_id,
            thread_id=inbound.thread_id,
        )


# pseudo-code — replace with real platform SDK functions
async def _open_platform_session(token: str) -> Any: ...
async def _close_platform_session(client: Any) -> None: ...
async def _platform_self_check(client: Any) -> dict[str, Any]: ...
```

## §4. Optional hooks (additive plugin extension)

Some plugin extensions are useful when present but not essential for the
subsystem to function. For these, the connector subsystem uses an
**optional-hook convention** rather than widening a Protocol:

- The consumer accesses the hook via `getattr(plugin, "<hook>", None)`
  and falls back to a sensible default at the call site if the attribute
  is absent.
- The hook is documented as an optional method on plugins but is NOT
  declared on the `ConnectorPlugin` Protocol at
  `the_one/connectors/base.py`.
- Plugins that implement an optional hook MUST tolerate the consumer's
  exception-catching behavior — the consumer catches any exception from
  the hook and uses the fallback. Plugin authors are NOT expected to
  never raise.

First instance: **`display_channel(envelope: InboundEnvelope) -> str`**
for session-title derivation in
`the_one.connectors._session._derive_title` (M10 F03 L03). Plugins that
implement it return a human-readable channel label
(e.g. `"#engineering"`, `"@alice"`); plugins that don't fall through to
`envelope.channel_id` at the resolver layer. `StubPlugin.display_channel`
is the reference implementation — returns `f"stub:{envelope.channel_id}"`.

When to add a method to the Protocol vs. use the optional-hook convention:

- **Protocol method**: every plugin MUST implement; the subsystem
  mechanically depends on it being callable (e.g.
  `ConnectorPlugin.connect`, `ConnectorPlugin.doctor`).
- **Optional hook**: most plugins benefit from implementing it but the
  subsystem has a working fallback without it; forcing every connector
  author to write a no-op stub would be friction (e.g.
  `display_channel`).

Future flights (notably F4's `ConnectorClient` outbound-send extension if
it lands as optional) may use the same pattern.

## §5. Test seams

Test code reaches into the subsystem via these named seams:

- `the_one.connectors.registry.register_for_test(type_name, plugin_class)` —
  register or overwrite a type without the collision check; for tests that
  swap plugins between cases.
- `the_one.connectors.registry.clear_for_test()` — empty the registry
  (hard clear; does NOT re-run `register_builtin_connectors`).
- `the_one.connectors.registry.restore_to_baseline_for_test()` — empty
  then re-run the builtin discovery hook so state matches what production
  code sees at module import time. In Flight 1 this is empty; Flight 8+
  the baseline contains the registered production types.
- `the_one.connectors._pool._clear_for_test()` — cancel the reaper task,
  empty `_pool`, cancel any worker tasks, reset `_shutting_down = False`
  and `_reaper_task = None`. M07's test-isolation lesson applied from day
  one. Tests should call this in an autouse fixture AFTER each test
  (sync fixture wrapping an async call, per the project's pytest-asyncio
  auto-mode setup).
- `the_one.connectors._stub.StubPlugin` / `StubClient` — rich in-process
  stub with class-level recording buffers (`connect_calls`,
  `disconnect_calls`, `doctor_calls`, `inbound_records`,
  `outbound_records`) and scenario knobs (`doctor_response`,
  `connect_should_fail`). Tests import directly from the canonical path:
  `from the_one.connectors._stub import StubPlugin, StubClient`. The
  stub is NOT registered via `register_builtin_connectors` — tests
  register it explicitly via `register_for_test("stub", StubPlugin)`.

Pool-internal tests (in `tests/test_connectors_pool.py`) and protocol /
registry tests (in `tests/test_connectors.py`) carry their own narrow
`_StubPlugin` / `_MinimalPlugin` helpers — those are intentionally
distinct from the rich `_stub.py` stub. The narrow helpers test pool /
protocol internals; the rich stub is the cross-flight regression
fixture that Flights 2–10 inherit.

## §6. The `'stub'` type name is reserved for tests

Production code MUST NOT register `'stub'` via
`register_builtin_connectors`. The v13/v14 schema has no CHECK constraint
on `connector_accounts.type` (Flight 1 ships without one — see `agents.md`
"Connector type extension checklist" layer 4), so storing `'stub'`-typed
rows in tests works at the persistence layer without polluting the
production type registry.

Flight 8's v15 migration adds the CHECK constraint when `'discord'`
becomes a real type to constrain — at that point `'stub'` will need to be
explicitly included in the CHECK constraint set OR the test-side seeding
will fail. Future flights touching the CHECK MUST coordinate with this
README and with `tests/test_connectors_e2e.py`.

## §7. Encryption envelope

`connector_accounts.secrets` is a JSON-encoded dict encrypted via
Fernet-symmetric using the system-wide encryptor
(`get_encryptor(settings.data_dir)`). `ConnectorAccountRepository` holds
the encryptor as a **reference, not copy** — post-rotation `install_key()`
propagates to live repository instances. The repository's
`_secrets_to_ciphertext` / `_ciphertext_to_secrets` envelope mirrors
`MCPSourceRepository` exactly.

`_ciphertext_to_secrets` swallows `InvalidToken` and returns `{}` (the
"migration residue" case) but propagates `JSONDecodeError` (the "real
corruption" case). Same shape as MCP — see `db/repositories.py` for the
canonical comments.

The `__MASKED__` sentinel is preserved in the update path: when an
operator submits a partial update that leaves `secrets` masked, the
repository detects the sentinel and preserves the stored ciphertext
(mirrors the LLM provider `api_key` `__MASKED__` contract).

## §8. Rotation invariant

`POST /api/encryption/rotate` (`interfaces/web/api.py:rotate_encryption_key`)
re-encrypts **three corpora atomically** in a single transaction:

1. `llm_providers.api_key`
2. `mcp_sources.secrets`
3. `connector_accounts.secrets`

A failure in any UPDATE branch rolls back all three; the single
`await conn.commit()` is the authoritative commit point and the new key
file is written to disk via `os.replace` only AFTER the DB commit
succeeds. See `agents.md`'s "Connector subsystem → Encryption-rotation
invariant" for the full discussion and rationale.

## §9. Cross-references

- **Connector subsystem decisions / invariants / known issues**: see
  `the_one/agents.md`'s "Connector subsystem" section. That section is
  the canonical reference for the typed-exception hierarchy, the
  worker-task-per-entry pattern, the parallel-pool-not-shared decision
  (with the explicit third-network-keyed-pool extraction trigger and
  the PTY-exclusion rationale), the per-Protocol structural-satisfaction
  discipline, the encryption-rotation invariant, and the two carry-
  forward Known Issues (deferred shared-pool extraction; Flight 3
  acquire-per-inbound ratification).
- **Connector type extension checklist** (the analog of the provider-type
  six-layer checklist): see `the_one/agents.md`'s "Connector type
  extension checklist" section.
- **MCP runtime invariants** (the precedent this subsystem mirrors —
  AsyncExitStack pattern, worker-task pattern, F4 pool semantics): see
  `the_one/mcp/README.md`.
- **Project-wide conventions** (`trust-the-runtime`,
  `canonical-import + convenience-re-export`,
  `structural-Protocol-satisfaction`, `verbatim-message-equality`): see
  `the_one/agents.md`'s "Project Conventions" section.
