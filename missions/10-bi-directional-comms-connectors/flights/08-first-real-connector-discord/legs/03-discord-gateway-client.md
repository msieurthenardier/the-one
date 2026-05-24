# Leg: discord-gateway-client

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Land the `DiscordClient` class wrapping `discord.py`'s `discord.Client`: implement `is_alive` against the SDK's connection state, place a `send` placeholder for L5, and fill in `DiscordPlugin.connect` and `DiscordPlugin.disconnect` to open and close the gateway lifecycle with intents (Message Content + Guild Members + Guilds), 5-attempt exponential-backoff reconnect (1s/2s/4s/8s/16s) for connect-time transient failures, and presence configuration (default "Watching agent traffic", operator-overridable via `account.config["presence"]`). The gateway sees no inbound message routing yet (L4 wires `on_message`); the pool sees a live client returned from `connect`.

## Context

L3 of F8. Per Design Decisions and L2's stateless DiscordPlugin shape:

- **`discord.py 2.4+` is pinned in `pyproject.toml`** (landed in L2). Use the SDK's connection primitives — do NOT hand-roll the WebSocket.
- **DiscordPlugin is stateless** — per-connection state lives on the `DiscordClient` instance L3 introduces. `DiscordPlugin.connect(account, encryptor)` constructs a `discord.Client` with the required intents, runs the connect handshake, and returns a `DiscordClient` wrapper that holds the SDK client + the connection task.
- **`discord.Client.start(token)` is blocking-until-disconnect** — the pool expects `connect` to return promptly. Use the SDK's separate `login(token)` + `connect()` (or `start()` in a background task with the pool's worker-task pattern) so the connection runs on its own asyncio task and `DiscordPlugin.connect` returns the `DiscordClient` wrapper as soon as the gateway READY event fires.
- **The pool's worker-task-per-entry pattern at `_pool.py:187-228`** — verified directly: the worker task awaits `plugin.connect()`, then `entry.evict_event.wait()`, then in `finally:` runs `plugin.disconnect()`. Both `connect` and `disconnect` calls run on the same task. **What happens INSIDE `connect` is plugin-internal**: the discord.py SDK requires a long-running asyncio task to run the gateway loop (`client.connect()` is blocking-until-disconnect). L3 spawns this background task INSIDE `DiscordPlugin.connect`, owned by the returned `DiscordClient` instance, and L3's `DiscordPlugin.disconnect` is responsible for cleanly terminating it. The anyio cross-task CancelScope guard at `agents.md` applies to the worker task itself (which is asyncio, not anyio); the spawned discord.py SDK task is plain asyncio with no anyio scope. **Critical invariant**: if `plugin.connect` raises mid-flight (e.g. on_ready timeout, retryable error after partial setup), it MUST clean up the spawned task before raising — the pool's `BaseException` catch at `_pool.py:211` would otherwise leak the task.
- **Reconnect — outer/inner division of labor**:
  - **Outer (L3 owns)**: 5-attempt exponential-backoff retry around the INITIAL pre-READY `connect()` call (e.g. fresh token rejection, DNS hiccup, gateway 5xx, on_ready timeout). After 5 attempts, raise `ConnectorConnectionError`.
  - **Inner (SDK owns)**: discord.py's `Client.connect(reconnect=True)` (the SDK default; what `Client.start` uses) auto-reconnects indefinitely for post-READY transient disconnects (RESUMED frames, brief network blips). L3 does NOT override this default.
  - **When the SDK's post-READY reconnect crashes terminally** (e.g. token revoked, intent now denied, fatal `ConnectionClosed` with no resume): the spawned background task exits with an exception → `is_alive()` returns False → pool reaper respawns on next acquire.
  - **Operator-bounded intra-session reconnect**: NOT in L3 scope. SDK default (unbounded) is acceptable for F8; F10 hardening can revisit if operator UX surfaces concrete cases.
- **F4's `send` widening of `ConnectorClient`** — `DiscordClient.send(target, content) -> SendResult` is required by the Protocol. L3 ships a placeholder that raises `NotImplementedError("M10 F8 L5 lands the outbound adapter")`. L5 fills in the real implementation against `discord.TextChannel.send` / `Thread.send`.

Key learnings from L1-L2:
- L2 confirmed the StubClient precedent at `_stub.py:43-69` — minimal `is_alive() -> bool` + `async send(target, content) -> SendResult`. DiscordClient mirrors the shape.
- L2 made DiscordPlugin stateless; the 4 method bodies were `NotImplementedError`. L3 fills in `connect` + `disconnect`; `doctor` and `normalize_session_key` stay `NotImplementedError` until L7 and L4.
- The pool's connect-failure handling (`_pool.py:_entry_worker`) catches exceptions and marks the entry as failed — exceptions propagate cleanly out of `DiscordPlugin.connect`.

## Inputs

Before this leg runs:

- `the_one/connectors/_discord.py` (from L2) carries `DiscordPlugin` skeleton — all 4 methods raise `NotImplementedError`.
- `the_one/connectors/_stub.py:43-69` defines `StubClient` shape — the precedent for `DiscordClient`.
- `the_one/connectors/base.py:236-274` declares `ConnectorClient` Protocol with `is_alive` + `send`.
- `the_one/connectors/_pool.py:187+` defines `_entry_worker` lifecycle pattern (connect + await eviction + disconnect — all on one task).
- `pyproject.toml` (from L2) pins `discord.py>=2.4,<2.5`; the SDK is installed in the dev container.
- `the_one/db/models.py` defines `ConnectorAccount` with `secrets: dict[str, Any]` (encrypted-then-decrypted via the encryptor); the convention is `secrets["BOT_TOKEN"]` for the Discord token.

## Outputs

After this leg completes:

- `the_one/connectors/_discord.py` adds:
  - `DiscordClient` class — wraps `discord.Client` + the connection background task; implements `is_alive` (checks `self._client.is_closed()` inverted, AND the connection task is not done with an exception, AND the client received a `READY` event), implements `send` as a placeholder (`NotImplementedError("M10 F8 L5 lands the outbound adapter")`).
  - `DiscordPlugin.connect` implementation:
    - Decrypts `account.secrets["BOT_TOKEN"]` via `encryptor.decrypt(...)` AT CALL TIME (does not retain the plaintext past the call).
    - Constructs `discord.Intents` with `message_content=True`, `members=True`, `guilds=True` (everything else default).
    - Constructs `discord.Client(intents=intents)`.
    - Reads `account.config.get("presence", {"name": "Watching agent traffic", "type": "watching"})` and sets the activity via `discord.Activity` / `discord.ActivityType`.
    - Outer reconnect loop: 5 attempts with exponential backoff (1s, 2s, 4s, 8s, 16s). Each attempt calls `client.login(token)` + `client.connect()` (or wraps via `client.start(token)` in a task). On `discord.errors.LoginFailure` / `discord.errors.PrivilegedIntentsRequired`, fail FAST — no retry (those are config errors, not transient). On `discord.errors.GatewayNotFound` / `discord.errors.ConnectionClosed` / `aiohttp.ClientError`, retry with backoff. After 5 failures, raise `ConnectorConnectionError("Discord gateway connect exceeded 5-attempt reconnect budget").`
    - On READY: returns a `DiscordClient` wrapping the live `discord.Client` + the background connection task.
  - `DiscordPlugin.disconnect` implementation:
    - Calls `client._client.close()` (gracefully closes the SDK client's connection).
    - Awaits the connection task (with a timeout, e.g. 5 seconds, to ensure clean teardown).
    - Pool guarantees `disconnect` runs on the same task as `connect` per the worker-task pattern.

- `tests/test_connectors_discord.py` (NEW) covers:
  - `DiscordClient.is_alive()` returns True when the wrapped client is open AND ready; False after `close()`.
  - `DiscordPlugin.connect` constructs intents correctly (`message_content=True`, `members=True`, `guilds=True`).
  - Reconnect: simulate 2 transient failures + 1 success → connect returns after 3 attempts.
  - Reconnect exhaustion: simulate 5 consecutive transient failures → `ConnectorConnectionError` raised.
  - Fail-fast: `LoginFailure` → no retry, immediate `ConnectorConnectionError` propagated.
  - Presence: default activity is "Watching agent traffic"; operator-override via `account.config["presence"]` is honored.
  - Token plaintext NOT retained BY THE PLUGIN OR CLIENT: after `connect` returns, neither `DiscordPlugin` nor `DiscordClient` has any attribute holding the plaintext token (no `_token`, `_bot_token`, etc.). The discord.py SDK retains the token internally for HTTP REST calls — that's the SDK's domain and is acceptable for the encryption-rotation invariant because pool eviction on credential change (`_pool.py:_evict_all_for_account`) destroys the SDK client instance and its internal token retention.
  - `send` placeholder raises `NotImplementedError` with the L5 marker (pin the contract until L5).
  - All tests use a mocked `discord.Client` (via `monkeypatch` or `unittest.mock`) — no real Discord connection.

- `the_one/connectors/_discord.py` module docstring updated to reflect L3's landing.

- `the_one/agents.md` Connector subsystem section (if it references intents / reconnect / presence) gains a one-paragraph note on the L3 gateway-client shape.

- F1-F7 + L1 + L2 test suite continues to pass; the new `test_connectors_discord.py` adds ~8 tests.

## Acceptance Criteria

- [ ] **`DiscordClient` class in `_discord.py`** — wraps `discord.Client` + the connection task. Instance fields:
  - `_client: discord.Client` — the wrapped SDK instance
  - `_connection_task: asyncio.Task[None]` — the spawned background task running the SDK gateway loop
  - `_ready_event: asyncio.Event` — set by the `on_ready` handler; the actual asyncio primitive (renamed from the cycle-1 leg's awkward `_ready_event_received: bool`)
  - `_user: discord.ClientUser | None` — the SDK's `client.user` captured at READY (for L7 doctor probe)
  - `_intents: discord.Intents` — the intents used at construction (for debug surface)
  
  `is_alive() -> bool` returns True when: `not (self._connection_task.done() and self._connection_task.exception() is not None)` AND `not self._client.is_closed()` AND `self._ready_event.is_set()`. Equivalent simpler form: the gateway task hasn't crashed AND the SDK hasn't been closed AND READY fired.
  
  `close()` method (new — addresses encapsulation): delegates to `self._client.close()` and awaits the connection task with a 5-second timeout, cancelling on timeout. `DiscordPlugin.disconnect(client)` calls `client.close()` instead of reaching into `client._client`.

- [ ] **`DiscordClient.send(target, content)` placeholder** — raises `NotImplementedError("M10 F8 L5 lands the outbound adapter — Discord text-channel and thread send wraps land there")`. Pin the contract: `isinstance(DiscordClient.__call_dummy__(), ConnectorClient)` returns True (the Protocol checks method names; placeholder still counts).

- [ ] **`DiscordPlugin.connect(account, encryptor)` implementation**:
  - Decrypts `account.secrets["BOT_TOKEN"]` exactly once at call time and passes directly to `client.login(token)`. The DiscordPlugin and DiscordClient do NOT retain the plaintext as instance attributes — the SDK retains it internally for HTTP REST calls, which is the SDK's domain and acceptable for the encryption-rotation invariant (credential rotation evicts the pool entry, destroying the SDK client + its retained token).
  - Constructs `discord.Intents` with `message_content=True, members=True, guilds=True`; all other intents default-False (SDK default for everything else).
  - Constructs `discord.Client(intents=intents)`.
  - Reads `account.config.get("presence")`; default is `{"name": "Watching agent traffic", "type": "watching"}` (which maps to `discord.ActivityType.watching`). Operator-override shapes accept `{"name": str, "type": Literal["playing", "watching", "listening", "competing"]}`.
  - Outer reconnect: 5 attempts with backoff `[1, 2, 4, 8, 16]` seconds. Retryable errors: `discord.errors.GatewayNotFound`, `discord.errors.ConnectionClosed`, `aiohttp.ClientError` (network), `asyncio.TimeoutError`. Non-retryable (fail-fast, no retry): `discord.errors.LoginFailure`, `discord.errors.PrivilegedIntentsRequired`. After 5 failed retries, raise `ConnectorConnectionError("Discord gateway connect exceeded 5-attempt reconnect budget; check token validity and intent configuration in the Discord Developer Portal")`.
  - On `on_ready` event from the SDK, sets `self._ready_event_received = True`; `connect` returns the `DiscordClient` wrapper.
  - The wrapping connection task is held on the `DiscordClient` instance and runs the SDK's `client.connect()` loop until disconnect.

- [ ] **`DiscordPlugin.disconnect(client)` implementation**:
  - Delegates to `client.close()` (the new method on `DiscordClient` that encapsulates SDK access).
  - Returns None.
  - Idempotent: a second call on an already-closed client is a no-op (no exception).

- [ ] **`tests/test_connectors_discord.py` ships (NEW)** with at least 8 test functions covering:
  - is_alive happy path (alive after connect; not-alive after disconnect).
  - Intent construction (message_content + members + guilds all True; everything else default-False).
  - Reconnect: 2 transient failures then success → 3rd attempt connects.
  - Reconnect exhaustion: 5 failures → `ConnectorConnectionError`.
  - Fail-fast: `LoginFailure` raised on first attempt → no retry, `ConnectorConnectionError` propagated.
  - Presence default: activity set to "Watching agent traffic" / ActivityType.watching when `account.config["presence"]` is absent.
  - Presence override: when `account.config["presence"] = {"name": "Playing chess", "type": "playing"}`, ActivityType.playing is set.
  - Token plaintext lifecycle: decrypted exactly once; plaintext NOT stored on the DiscordPlugin or DiscordClient instances (asserted by `hasattr` check); SDK-internal retention is out of scope (the SDK needs it for HTTP REST).
  - `send` placeholder raises `NotImplementedError` with the L5 marker (pin until L5 fills in).
  
  Tests use `monkeypatch.setattr` patching the **consumer import** (`monkeypatch.setattr("the_one.connectors._discord.discord", stub_discord_module)`) rather than the source attribute — the existing `tests/test_connectors_pool.py` pattern is the precedent (`monkeypatch.setattr(pool_mod, "_load_account", ...)`). For the SDK Client construction, mock the discord module's `Client` attribute with an `unittest.mock.AsyncMock`-equipped stub that records constructor args + exposes `login` / `connect` / `close` as awaitable coroutines. Use `asyncio.Event` in tests to control when `on_ready` fires (simulate by calling the registered event handler directly). NO real Discord connection. NO network calls.

- [ ] **`DiscordPlugin.connect` does NOT instantiate `DiscordClient` until READY** — the connection-task model fires `on_ready` before `connect` returns. Tests assert that `connect` does NOT return until the simulated `on_ready` event fires.

- [ ] **F1-F7 + L1-L2 regression**: `docker exec the-one pytest tests/ -x --timeout 30` passes — count goes from 2272 to ~2280 (adds ~8 new tests in `test_connectors_discord.py`).

## Verification Steps

- `grep -c "class DiscordClient" the_one/connectors/_discord.py` — exactly 1.
- `grep -c "intents.message_content\|message_content=True" the_one/connectors/_discord.py` — at least 1.
- `grep -c "ConnectorConnectionError" the_one/connectors/_discord.py` — at least 1 (the budget-exhausted raise).
- `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30` — all pass; at least 8 tests.
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes.
- `docker exec the-one python -c "from the_one.connectors._discord import DiscordClient, DiscordPlugin; from the_one.connectors.base import ConnectorClient, ConnectorPlugin; assert isinstance(DiscordPlugin(), ConnectorPlugin); print('OK')"` — prints OK.

## Implementation Guidance

Order surfaces by dependency:

1. **`DiscordClient` class** — define the wrapper first; methods reference `self._client`, `self._connection_task`, `self._ready_event_received`. Implement `is_alive` and `send` (placeholder).
2. **Reconnect logic helper** — extract a private `_connect_with_backoff(client, token)` async function that runs the 5-attempt loop. Easier to test in isolation.
3. **`DiscordPlugin.connect`** — wires the helper, sets up intents, presence, on_ready handler, returns the wrapper.
4. **`DiscordPlugin.disconnect`** — graceful close + task await with timeout.
5. **Tests** — mock-based; use `pytest-asyncio` (already in the project's test deps per F1). Pattern: monkeypatch `discord.Client` with a stub that records constructor args and exposes `login` / `connect` / `close` as awaitable mocks; use `asyncio.Event` to simulate `on_ready`.
6. **Module docstring update** — reflect L3's landing.
7. **Full-suite green** — `docker exec the-one pytest tests/ -x --timeout 30`. Update flight log.

### Code patterns to follow

- **`OutboundTarget` and `SendResult`** at `base.py:85+, 149+` — `send` placeholder must use these signatures even if the body just raises.
- **`ConnectorConnectionError`** at `connectors/errors.py` — the F1-typed exception for connection failures; use this for budget-exhausted, NOT a bare RuntimeError.
- **`Encryptor.decrypt(...)`** at `the_one.encryption:Encryptor` — the contract for decrypting `account.secrets[...]`. Pass the encrypted value; receive plaintext bytes/str.
- **`pytest-asyncio` async tests** — mirror existing async test patterns in `tests/test_connectors_pool.py` for fixture and assertion shape.

## Edge Cases

- **Background task crashes mid-connection** (e.g. SDK raises `ConnectionClosed` after READY): `is_alive` returns False (the task is done-with-exception). Pool reaper evicts; next acquire respawns. Log via `logger.exception` so operators can debug.
- **`account.config["presence"]` has malformed shape** (e.g. `{"name": 123, "type": "invalid"}`): coerce or fall back to defaults silently; log a warning. Do NOT fail `connect` over presence — it's cosmetic. Test pinning this fallback.
- **Discord rate-limits the connection attempt**: SDK raises `discord.errors.HTTPException(429)`. Treat as retryable (counts toward the 5-attempt budget). After exhaustion, the budget-exceeded error message hints "platform may be rate-limiting; retry later."
- **Privileged intents not enabled in Developer Portal**: SDK raises `PrivilegedIntentsRequired`. Fail-fast — no retry. Error message hints "enable Message Content and Guild Members intents in https://discord.com/developers/applications/{app_id}/bot."
- **Token plaintext leakage**: tests assert the plaintext is NOT stored on the plugin or client. Mechanism: pass the plaintext directly to `client.login(token)` then let it go out of scope; do NOT assign to `self._token`.
- **`on_ready` never fires** (e.g. SDK hangs in handshake): the connect call would block indefinitely. Add `asyncio.wait_for` around the on_ready event with a **60-second** default timeout (override via `account.config.get("ready_timeout_seconds", 60)`); 60s accommodates cold-start with `members=True` chunking on large guilds. On timeout, cancel the spawned background task, then treat as retryable and try the next attempt. Test this.
- **`PrivilegedIntentsRequired` raise origin**: discord.py 2.4+ raises `PrivilegedIntentsRequired` from `Client.connect()` (gateway IDENTIFY), NOT from `Client.login()` (HTTP token check). The fail-fast catch in the outer reconnect loop MUST wrap the connect step, not just login.
- **`reconnect=True` SDK default is unbounded**: discord.py's `Client.connect(reconnect=True)` (the SDK default when used via `Client.start`) auto-reconnects indefinitely after READY. L3 inherits this default — operators wanting bounded intra-session reconnect must wait for F10 hardening. Document in the leg log.
- **Spawned-task cleanup on `connect` error**: if `plugin.connect` raises mid-flight (e.g. on_ready timeout, retryable error after `client.login` already returned), the spawned background task MUST be cancelled before raising — otherwise `_pool.py:211`'s `BaseException` catch propagates the error to acquire callers while the task leaks. Wrap the post-`client.login` setup in `try/except` that cancels the spawned task before re-raising.

## Files Affected

- `the_one/connectors/_discord.py` — `DiscordClient` class + `DiscordPlugin.connect/disconnect` bodies + module docstring update
- `tests/test_connectors_discord.py` (NEW) — gateway client tests
- `the_one/agents.md` — Connector subsystem note on L3 gateway-client shape (optional; add if there's a natural spot)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`docker exec the-one pytest tests/ -x --timeout 30`)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit — wait for flight-level review per `/agentic-workflow`

## Citation Audit

Citations verified at leg-design time:
- `the_one/connectors/_discord.py` — exists (created by L2); `DiscordPlugin` class skeleton present — **OK**
- `the_one/connectors/_stub.py:43-69` — `StubClient` shape — **OK** (verified)
- `the_one/connectors/base.py:236-274` — `ConnectorClient` Protocol — **OK** (verified)
- `the_one/connectors/_pool.py:187+` — `_entry_worker` lifecycle — **OK** (verified)
- `the_one/connectors/errors.py:ConnectorConnectionError` — F1-shipped typed exception — **OK** (named in agents.md)
- `pyproject.toml` `discord.py>=2.4,<2.5` — landed by L2 — **OK** (L2 commit)

6 citations verified against current code at leg design time.
