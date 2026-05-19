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
│                      # DoctorReport). Home of F6's resolver outcome ADT
│                      # (Permit / NeedsPairing / Deny + ResolveOutcome) and the
│                      # _default_permit fallback. Future home of CommandHandler
│                      # (Flight 7).
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
- `ConnectorClient` (Flight 1, widened in Flight 4) — `is_alive` + `send`
  (2 methods). The per-instance live-connection wrapper returned by
  `ConnectorPlugin.connect`. F4 widened this Protocol with `send` so the
  ``platform_send`` built-in tool can dispatch outbound platform-bound
  messages through every plugin uniformly.
- Optional `resolve` hook (Flight 6) — ACL-aware connectors expose a
  per-(peer, channel) gating hook discoverable via `getattr` (see §4 below
  and `optional-plugin-hook-via-getattr-sentinel` in `agents.md`); NOT
  declared on the `ConnectorPlugin` Protocol.
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
    OutboundTarget,
    SendResult,
    SessionKey,
)
from the_one.db.models import ConnectorAccount
from the_one.encryption import Encryptor


class HypotheticalPlatformClient:
    """Structural ConnectorClient — ``is_alive`` + ``send``."""

    def __init__(self, platform_session: Any) -> None:
        self._session = platform_session

    def is_alive(self) -> bool:
        return self._session.is_open()  # pseudo-code

    async def send(
        self, target: OutboundTarget, content: str
    ) -> SendResult:
        # pseudo-code — real SDK call to deliver `content` to `target`:
        platform_msg = await self._session.post(
            channel_id=target.channel_id,
            thread_id=target.thread_id,
            content=content,
        )
        return SendResult(
            platform_message_id=platform_msg.id,
            details={"channel": target.channel_id},
        )


class HypotheticalPlatformPlugin:
    """Structural ConnectorPlugin — ``connect`` + ``disconnect`` + ``doctor`` +
    ``normalize_session_key``. ``connect()`` returns a ``HypotheticalPlatformClient``.
    No inheritance per ``structural-Protocol-satisfaction``."""

    async def connect(
        self, account: ConnectorAccount, encryptor: Encryptor
    ) -> ConnectorClient:
        secrets = account.secrets  # already-decrypted dict from the repository
        token = secrets["bot_token"]
        # pseudo-code — replace with real SDK call:
        platform_session: Any = await _open_platform_session(token)
        return HypotheticalPlatformClient(platform_session)

    async def disconnect(self, client: ConnectorClient) -> None:
        # pseudo-code — idempotent close; do not raise if already closed
        await _close_platform_session(client)

    async def doctor(
        self, account: ConnectorAccount, encryptor: Encryptor
    ) -> DoctorReport:
        try:
            client = await self.connect(account, encryptor)
        except Exception as e:  # noqa: BLE001 — doctor surfaces failure, not raises
            return DoctorReport(status="failed", message=str(e), details={})
        try:
            # pseudo-code — minimal handshake probe; no message dispatch to peers
            info = await _platform_self_check(client)
            return DoctorReport(
                status="ok",
                message=f"connected as {info['bot_user']}",
                details={"identity": info["bot_user"]},
            )
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

Second instance: **`resolve(account: ConnectorAccount, envelope: InboundEnvelope) -> ResolveOutcome`**
for per-(peer, channel) gating in `the_one.connectors._inbound.dispatch_inbound`
and `the_one.tools.connector_send.SendToPlatformChannelTool.execute`
(M10 F06 L2 + L3). Plugins that implement it return one of three outcomes:
`Permit()` (admit), `NeedsPairing(reason)` (dispatcher validates a pairing
prefix), or `Deny(reason)` (reject silently). Plugins that don't implement
it fall through to `_default_permit` at the consult sites — always
`Permit()`. The `StubPlugin` does NOT implement `resolve`; F1–F5
regression coverage exercises the `_default_permit` path. The hook uses
a named-callable fallback (`_default_permit`) rather than the `None`
sentinel that `display_channel` uses, because the default outcome is
structured (a `Permit()` instance) rather than implicit.

When to add a method to the Protocol vs. use the optional-hook convention:

- **Protocol method**: every plugin MUST implement; the subsystem
  mechanically depends on it being callable (e.g.
  `ConnectorPlugin.connect`, `ConnectorPlugin.doctor`).
- **Optional hook**: most plugins benefit from implementing it but the
  subsystem has a working fallback without it; forcing every connector
  author to write a no-op stub would be friction (e.g.
  `display_channel`).

F4's `ConnectorClient.send` extension landed as **Protocol-widening**, NOT
optional-hook — outbound is required by every connector in scope, so
widening is the right shape (see §10 below and the
`protocol-widening-for-required-capability` convention in
`the_one/agents.md`). The `display_channel` precedent above remains the
canonical optional-hook example. Future plugin extensions choose between
the two patterns based on whether ALL plugins in scope must implement
(widen) or only some benefit from implementing (optional hook).

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
`register_builtin_connectors`. Schema versions before v19 have no CHECK
constraint on `connector_accounts.type` (Flight 1 ships without one — see
`agents.md` "Connector type extension checklist" layer 4), so storing
`'stub'`-typed rows in tests works at the persistence layer without
polluting the production type registry.

Flight 8's v19 migration adds the CHECK constraint when `'discord'`
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

## §10. Required capabilities (Protocol-widening)

F4 widened `ConnectorClient` with `async def send(target: OutboundTarget, content: str) -> SendResult` (Mission 10 leg 1 of Flight 4). Every connector in scope (stub, Discord at F8, the second connector at F9) MUST implement this method — outbound is the only path from agent to platform, and the `SendToPlatformChannelTool` (the sole production caller) depends on the method being callable.

The widening is non-breaking for existing implementations that already provide all the methods the widened Protocol requires. A class missing the new method fails the `runtime_checkable` isinstance check after widening — Python's Protocol semantics check method-name presence at call time, not at type definition. `tests/test_connectors.py::test_client_missing_send_fails_check` pins this behavior.

The convention is codified in `the_one/agents.md` Project Conventions as `protocol-widening-for-required-capability`. Choose Protocol-widening over the optional-hook convention (§4 above) when every plugin in scope MUST implement; choose optional-hook when most plugins benefit but a sensible default exists at the call site (e.g. `display_channel` fallback to `envelope.channel_id`).

## §11. Outbound flow trace

End-to-end walk of an outbound delivery, from the agent's tool call to the platform message:

1. **Agent invokes the tool**. The LLM's response includes a tool_call with `name="send_to_platform_channel"` and arguments `{target: {account_id, channel_id, thread_id?}, content}`. Agent core dispatches via `the_one/agent/core.py:Agent._execute_tool` (the existing per-tool dispatch path).

2. **Tool execute() validates target**. `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute()` validates the `target` shape (account_id, channel_id present; thread_id optional), validates `target.account_id ∈ self._connector_account_ids` (account-scope check; rejects with `[error] [constraint]` on mismatch). It then consults the channel + per-agent ACL gates: a per-call `ConnectorAccountRepository.get(account_id)` fetch reads current account state, and the tool intersects `target.channel_id` against (i) account-scope `account.config["allowlist"]["channels"]` (absent → permit) and (ii) per-agent `AgentConfig.connector_acls[account_id]["channels"]` (account_id key absent or empty channels list → inherit). Denials return the standard `[error] [constraint]` envelope. Source of truth: `connector_send.py:execute` + `AgentConfig.connector_acls`.

3. **Tool acquires pool entry**. The tool calls `the_one/connectors/_pool.py:acquire(agent_name, account_id)` to fetch the warm `ConnectorClient`. The pool's worker-task-per-entry pattern ensures `connect` and `disconnect` run on the same task (anyio cross-task `CancelScope` safety). `last_activity` is touched on every successful resolve. Pool errors (`KeyError` for unknown account, `ConnectorRegistrationError` for unregistered plugin type, `ConnectorClientError` subtypes for connect failures, `RuntimeError` during shutdown) surface as `[error] <ExceptionType>: <message>` envelopes.

4. **Tool calls `client.send`**. `await client.send(target_obj, content)` returns a `SendResult` (`platform_message_id: str | None`, `details: dict`). `ConnectorClientError` subtypes raised from `send` (e.g. `ConnectorRateLimitError`, `ConnectorConnectionError`) surface as the same `[error] <ExceptionType>: <message>` envelope.

5. **Tool returns the success sentinel**. Format: `f"{PLATFORM_SEND_OK_PREFIX} sent to {account_id}:{channel_id}{thread_clause}: {content!r} (msg_id={result.platform_message_id})"`. The `PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` constant lives in `the_one/connectors/__init__.py` and is the single cross-module contract between the tool and the dispatcher.

6. **Agent appends the tool_result message**. Standard agent core dispatch — the tool's return string becomes a `Role.TOOL` `Message` with `tool_result.tool_call_id` matching the original tool_call's `id`.

7. **Dispatcher tags visibility post-step**. `the_one/connectors/_inbound.py:dispatch_inbound`'s post-step pass walks new messages: the tool_result whose parent tool_call had `name == "send_to_platform_channel"` AND whose content starts with `PLATFORM_SEND_OK_PREFIX` gets `visibility=None` (platform-visible). Other assistant / tool-result messages produced during the turn get `visibility=OPERATOR_VISIBILITY`.

8. **Dispatcher persists**. The whole updated `agent.messages` history (including the now-tagged messages) is encoded via `the_one/db/codec.py:encode_messages` and written via `ChatSessionRepository.update`. F5's Chat UI consumes the `visibility` tag for two-layer rendering.
