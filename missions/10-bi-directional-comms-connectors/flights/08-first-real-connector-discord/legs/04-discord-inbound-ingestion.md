# Leg: discord-inbound-ingestion

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Wire Discord's `on_message` event to the F7 inbound dispatcher: implement `DiscordPlugin.normalize_session_key` (currently `NotImplementedError`), ship a pure-function `_translate_discord_message_to_envelope` helper in a new module (`_discord_translate.py`) that converts a `discord.Message` into an `InboundEnvelope`, register the `on_message` event handler on the SDK client during `DiscordPlugin.connect` (extending L3's connect path), and have the handler call `dispatch_inbound(account_id, envelope, factory=...)` per F7. Filter out bot's own messages and other-bots' messages by default (operator-overridable via `account.config["ingest_bots"]`). The translate helper lives in a pure-function module so it's unit-testable against recorded discord.Message fixtures without spinning up the gateway.

## Context

L4 of F8. Per flight Design Decisions:

- **`_translate_discord_message_to_envelope` lives in a pure-function module** (`_discord_translate.py` or `_discord/_translate.py`) per F7 debrief Key Learning #1 ("pure-function module with `__all__`"). Easier to unit-test against recorded fixtures than against a connected gateway.
- **`envelope.raw` carries Discord-specific fields**: `is_dm: bool` (set here for L6's `is_dm` hook), `guild_id: str | None`, `attachments: list[...]`, `member_roles: list[str]`, and the raw `discord.Message` reference. The L8 allowlist axes extension (guilds + roles) consults `raw["guild_id"]` and `raw["member_roles"]`. The `is_dm` field is the L6 consult value.
- **`on_message` filter — ignore bots by default**: `message.author.bot == True` → skip ingestion. Operator override via `account.config["ingest_bots"] = True` if they need bot-to-bot conversations. Default False prevents infinite loops where the bot's own outbound messages trigger inbound ingestion.
- **F3 session-key normalization shape**: per the F3 flight, channel + thread + peer are the canonical key components. DMs collapse `guild_id` to None and use channel_id (Discord's DM channel id) as the binding. Threads carry their own `thread_id` distinct from the parent channel. `peer_id` is the message author's user id.
- **No agent-loop changes**: L4 only wires the dispatcher; agent.step is called by the F7 dispatcher, not directly by L4.
- **Stateless plugin**: `normalize_session_key` is `def` (sync) per the StubPlugin precedent at `_stub.py:200`.

Key learnings from L1-L3:
- L3 wired `on_ready` via the SDK's event-handler mechanism. L4 wires `on_message` using the same mechanism (`@client.event` decorator or `client.event(coro)` registration during `DiscordPlugin.connect`).
- L3's reconnect-on-failure means the on_message handler will fire across SDK-internal reconnects automatically; no L4-specific reconnect work.
- L3's connection task lifetime is managed by the pool's worker-task pattern; the on_message handler runs in the SDK's event loop on the same task.
- F7 dispatcher's `BaseException` catch and graceful-failure isolation mean an on_message handler exception will be logged by the dispatcher; the gateway loop continues.

## Inputs

Before this leg runs:

- `the_one/connectors/_discord.py` (post-L3) — `DiscordClient` class + `DiscordPlugin.connect/disconnect` working; `normalize_session_key` still raises `NotImplementedError`; `doctor` still raises NotImplementedError (L7).
- `the_one/connectors/_stub.py:200-207` — `StubPlugin.normalize_session_key` precedent (5-field SessionKey construction).
- `the_one/connectors/base.py:39-81` — `InboundEnvelope` dataclass with `platform`, `account_id`, `channel_id`, `thread_id`, `peer_id`, `peer_name`, `text`, `raw: dict[str, Any]`.
- `the_one/connectors/base.py:96-114` — `SessionKey` dataclass with `platform`, `account_id`, `channel_id`, `thread_id`, `peer_id`.
- `the_one/connectors/_inbound.py:156+` — `dispatch_inbound(account_id, envelope, *, factory)` — the dispatcher entry point.
- `the_one/connectors/_session.py:141` — `plugin.normalize_session_key(envelope)` is called by the session resolver; L4's implementation slots in here.
- `the_one/agent/factory.py` — `AgentFactory` instance the dispatcher needs. The plugin needs access to it (passed in via `__init__` would violate L2's stateless contract; the gateway handler can grab it from a module-level singleton or via the pool's lifecycle).
- F1-F7 + L1-L3 test suite green on branch `flight/08-planning-discord`.

## Outputs

After this leg completes:

- `the_one/connectors/_discord_translate.py` (NEW) — pure-function module exporting:
  - `_translate_discord_message_to_envelope(message: discord.Message, account_id: str) -> InboundEnvelope` — converts a `discord.Message` to the canonical envelope. Populates `raw` with `{"is_dm": bool, "guild_id": str | None, "attachments": list, "member_roles": list[str], "discord_message": message}`.
  - `__all__ = ("_translate_discord_message_to_envelope",)`.
  - Pure function: no I/O, no side effects, deterministic on input. Module docstring cites M10 F8 L4.

- `the_one/connectors/_discord.py` updated:
  - `DiscordPlugin.normalize_session_key(envelope)` implementation: returns `SessionKey(platform=envelope.platform, account_id=envelope.account_id, channel_id=envelope.channel_id, thread_id=envelope.thread_id, peer_id=envelope.peer_id)` — mirrors StubPlugin's pattern verbatim per F3's normalization shape (channel + thread + peer all participate).
  - `DiscordPlugin.connect` extended to register an `on_message` handler on the SDK client. The handler:
    1. Returns immediately if `message.author.bot` AND `not account.config.get("ingest_bots", False)` (default-filter).
    2. Returns immediately if `message.author.id == client.user.id` (defensive — never ingest our own messages even if `ingest_bots` is True).
    3. Translates via `_translate_discord_message_to_envelope(message, account.id)`.
    4. Calls `dispatch_inbound(account.id, envelope, factory=<factory>)` — factory access discussed below.
    5. Wraps in try/except + `logger.exception` to ensure handler errors don't kill the gateway loop.

- **Factory access pattern (resolved at design)**: option **(b) — module-level accessor in `the_one.agent.factory`**. The Developer cycle-1 review surfaced that option (c) ("set `client.factory` post-acquire") is unworkable because the on_message handler fires from INSIDE the pool's `_entry_worker` task (the listener spawns during `plugin.connect`), BEFORE any caller has a handle to set attributes on. The existing precedent at `interfaces/web/app.py:188` (`_get_factory()` reading from `_state["factory"]`) is exactly the module-level accessor pattern.
  - **L4 adds**: `set_factory(factory: AgentFactory) -> None` and `get_factory() -> AgentFactory | None` to `the_one/agent/factory.py`. Module-level `_factory: AgentFactory | None = None` storage.
  - **L4 wires `app.py` lifespan** to call `set_factory(...)` once at startup (alongside the existing `_state["factory"]` assignment at `app.py:81`).
  - **The on_message handler** calls `get_factory()` at dispatch time and falls through to log-and-return if None (defensive — test mocks may not set it).
  - **Same pattern applies to F9 (Slack) and beyond** — single module-level setter; all gateway listeners read via `get_factory()`.

- `tests/test_connectors_discord_translate.py` (NEW) — pure-function tests against recorded fixtures (synthetic `discord.Message` mocks):
  - Translate a guild-text-channel message → envelope with `is_dm=False`, `guild_id` populated, `channel_id` set, `thread_id=None`.
  - Translate a thread message → envelope with `thread_id` populated.
  - Translate a DM → envelope with `is_dm=True`, `guild_id=None`, `channel_id` = DM channel.
  - Member roles populated from `message.author.roles` (a sequence of `discord.Role` with `.id`).
  - `peer_name` populated from `message.author.display_name`.
  - Attachments captured in `raw["attachments"]` (basic shape; full handling deferred).
  - Empty message text (image-only message) → `envelope.text = ""`.

- `tests/test_connectors_discord.py` extended with on_message integration tests:
  - Bot-filtered: `message.author.bot=True`, `ingest_bots` absent → handler returns without dispatching.
  - Bot-allowed: `message.author.bot=True`, `account.config["ingest_bots"]=True` → handler dispatches.
  - Self-filtered: `message.author.id == client.user.id` → handler returns without dispatching even if `ingest_bots=True`.
  - Happy path: human user sends a message → `dispatch_inbound` called with correct envelope.
  - Handler exception swallowed: dispatcher raises mid-flight → handler logs and returns; gateway loop continues (no propagation).
  - Factory unavailable (`client.factory is None`): handler logs and returns gracefully (no crash).

- `DiscordPlugin.normalize_session_key` test (in `test_connectors_discord.py` or `test_connectors_discord_translate.py`):
  - Returns `SessionKey` with all 5 fields populated from the envelope.
  - Hashable / equality contract.

- `the_one/agents.md` Connector subsystem section adds a one-paragraph note on the `client.factory` post-acquire pattern (if option (c) is taken) — this is a new convention to codify.

- F1-F7 + L1-L3 regression: 2288 → ~2300 (12+ new tests).

## Acceptance Criteria

- [ ] **`_discord_translate.py` ships** as a pure-function module with `_translate_discord_message_to_envelope(message, account_id) -> InboundEnvelope`. Module-level `__all__` exports the helper. No I/O, no logging at the module/function level beyond what the dataclass construction requires. Module docstring cites M10 F8 L4.

- [ ] **Translate helper populates the full envelope correctly**:
  - `platform="discord"`
  - `account_id=<passed in>`
  - **Thread/channel convention (revised per cycle-1 review)**: `channel_id` is the **parent channel id**; `thread_id` is the thread's id when in a thread, `None` otherwise. This preserves F3's "this thread belongs to channel C" semantic in the `(channel_id, thread_id)` lookup tuple at `_session.py:146-151`.
  - For a top-level guild text-channel message: `channel_id=str(message.channel.id)`, `thread_id=None`.
  - For a thread message (`message.channel.type in (discord.ChannelType.public_thread, discord.ChannelType.private_thread)`): `channel_id=str(message.channel.parent.id)`, `thread_id=str(message.channel.id)`.
  - For a DM (`message.channel.type == discord.ChannelType.private`): `channel_id=str(message.channel.id)`, `thread_id=None`.
  - `peer_id=str(message.author.id)`
  - `peer_name=message.author.display_name` (NOT `name` — display_name reflects guild nickname when present, falls back to global username; matches what peers see in the UI)
  - `text=message.content` (the raw text; discord.py strips markdown? NO — content is the raw text with mentions as `<@id>` etc. Acceptable for F8; pretty-printing deferred to L5/L7 hardening.)
  - `raw={"is_dm": message.channel.type == discord.ChannelType.private, "guild_id": str(message.guild.id) if message.guild else None, "attachments": [a.to_dict() for a in message.attachments], "member_roles": [str(r.id) for r in getattr(message.author, "roles", [])], "discord_message": message}` (last field carries the raw SDK object for any L5+ handler that needs it).

- [ ] **`DiscordPlugin.normalize_session_key(envelope)` implementation**:
  - Returns `SessionKey(platform=envelope.platform, account_id=envelope.account_id, channel_id=envelope.channel_id, thread_id=envelope.thread_id, peer_id=envelope.peer_id)`.
  - Sync function (matches StubPlugin precedent at `_stub.py:200`).
  - No side effects.

- [ ] **`on_message` event handler registered in `DiscordPlugin.connect`**. After L3's `client = discord.Client(intents=intents)` construction and before `client.login(token)`, register the handler via `@client.event` or `client.event(on_message)`. The handler:
  - Filters bot messages (`message.author.bot` AND `not account.config.get("ingest_bots", False)`).
  - Filters self-messages (`message.author.id == client.user.id`) defensively (always-on).
  - Translates via the L4 helper.
  - Dispatches via `dispatch_inbound(account.id, envelope, factory=<resolved>)`.
  - Wraps the dispatch in try/except + `logger.exception` so handler errors don't kill the gateway loop.

- [ ] **Factory resolution — module-level accessor (option b)**:
  - `the_one/agent/factory.py` exports `set_factory(factory: AgentFactory) -> None` and `get_factory() -> AgentFactory | None`. Module-level storage `_factory: AgentFactory | None = None`. Both functions are sync; thread-safe is not required (set called once at lifespan startup).
  - `the_one/interfaces/web/app.py` lifespan (`startup`) calls `set_factory(_state["factory"])` after constructing the `AgentFactory` at `app.py:81`. The lifespan teardown calls `set_factory(None)` to release the reference (defensive, not required for correctness).
  - The on_message handler in `_discord.py` calls `get_factory()` at dispatch time. If `None`, logs at WARNING and returns (no exception) — defensive against pre-startup race or test mocks.
  - **Codify in `agents.md`** Connector subsystem section: "Gateway listeners spawned inside `plugin.connect` resolve their `AgentFactory` via `the_one.agent.factory.get_factory()`, set once at FastAPI lifespan startup. This decouples the listener's factory access from the pool's per-(agent, account) acquire signature."

- [ ] **`tests/test_connectors_discord_translate.py` ships** with at least 7 tests:
  - guild text channel translation
  - thread translation (verify channel_id vs thread_id convention)
  - DM translation (is_dm=True, guild_id=None)
  - empty text (image-only message)
  - peer_name = display_name (NOT global name)
  - attachments captured in raw
  - member_roles captured in raw (empty when no guild)

- [ ] **`tests/test_connectors_discord.py` extended** with on_message integration tests (at least 6):
  - bot-filtered (default)
  - bot-allowed (ingest_bots=True)
  - self-filtered (always-on)
  - happy path: human message → dispatch_inbound called with correct envelope (mocked)
  - handler exception swallowed (dispatcher raises, logged, gateway loop continues)
  - factory unavailable: handler logs and returns gracefully

- [ ] **`DiscordPlugin.normalize_session_key` test** in either of the new test files: pin the 5-field SessionKey construction.

- [ ] **`agents.md` Connector subsystem section** adds a paragraph on the `client.factory` post-acquire convention (new in F8 L4; will apply to F9 Slack and beyond).

- [ ] **F1-F7 + L1-L3 regression**: `docker exec the-one pytest tests/ -x --timeout 30` passes — count goes from 2288 to ~2300.

## Verification Steps

- `grep -c "_translate_discord_message_to_envelope" the_one/connectors/_discord_translate.py` — at least 1 (the function declaration).
- `grep -c "@client.event\|client.event(on_message)" the_one/connectors/_discord.py` — at least 1.
- `grep -c "ingest_bots" the_one/connectors/_discord.py` — at least 1.
- `docker exec the-one pytest tests/test_connectors_discord_translate.py tests/test_connectors_discord.py -x --timeout 30` — all pass.
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes.

## Implementation Guidance

1. **`_discord_translate.py` helper first** (pure function, easy to test). Build against fixture-style mock `discord.Message` objects.
2. **Translate-helper tests** (`test_connectors_discord_translate.py`). Pin the envelope shape against the fixture inputs.
3. **`DiscordPlugin.normalize_session_key` body** — trivial 5-line implementation mirroring StubPlugin. Single test.
4. **`DiscordPlugin.connect` extension** — register on_message handler. Wire bot/self filters. Wire dispatch via `dispatch_inbound`. Use the `client.factory` post-acquire pattern.
5. **on_message integration tests** in `test_connectors_discord.py`. Mock the factory + dispatcher; assert dispatch is called with the right envelope under happy path; filtered scenarios assert dispatch is NOT called.
6. **`agents.md` codification** — add the `client.factory` post-acquire convention paragraph in the Connector subsystem section.
7. **Full-suite green**.

### Code patterns to follow

- **Pure-function module with `__all__`** — see `the_one/connectors/_commands.py` for the F7 L1 precedent (`_parse_command`).
- **`StubPlugin.normalize_session_key` at `_stub.py:200`** — verbatim 5-line implementation.
- **Discord.py `on_message` decorator** — `@client.event async def on_message(message): ...` — standard SDK pattern.
- **`logger.exception` in the handler** — match the existing F7 dispatcher's error-logging style at `_inbound.py:401, 421, 437, 501, 527, 555` (multiple call sites; pick the closest semantic match, likely the dispatch-inbound entry-failure pattern).

## Edge Cases

- **Message with no content (image/embed only)**: `message.content` is `""`. Acceptable — `envelope.text=""` is valid. The agent sees an empty text plus attachments in `raw["attachments"]`; tool calls (e.g. an attachment-extraction tool) can handle.
- **Message in a thread**: `message.channel.type` is `ChannelType.public_thread` or `ChannelType.private_thread`. `channel_id` is the thread's id; `thread_id` is the same id; `raw["parent_channel_id"]` carries the parent. Test pins this.
- **DM channel**: `message.channel.type == ChannelType.private`. `message.guild is None` → `raw["guild_id"] = None`. `raw["is_dm"] = True`. `member_roles = []` (no roles in DM context).
- **Forwarded message / system message**: `message.type != discord.MessageType.default`. **Filter**: only ingest `MessageType.default` and `MessageType.reply` (operator-overridable via `account.config["ingest_message_types"]`?). Defer the override to F10 hardening; for F8, hard-filter to default+reply.
- **`client.user` not yet set when on_message fires**: shouldn't happen (on_ready fires before on_message), but defensive — if `client.user is None`, the self-filter check `message.author.id == client.user.id` would crash. Guard with `client.user is not None`.
- **Factory unset during a race**: `get_factory()` returns None during pre-lifespan-startup or post-shutdown. Handler logs at WARNING and returns; the platform message is effectively dropped (acceptable for the brief race window).
- **Listener startup gap — explicitly deferred to L11 HAT integration**: L4 wires the on_message handler INSIDE `plugin.connect`. For the listener to actually run, someone has to call `pool_acquire(...)` against the Discord account at startup — `plugin.connect` is what spins up the listener task. Today no production code does this; tests call `dispatch_inbound` directly. **L4 does NOT add lifespan-time auto-acquire** — that's L11 HAT integration territory (the operator wires "on startup, walk discord-typed accounts and warm-acquire each so listeners spin up"). Until L11 lands the lifespan wiring, the only way to drive end-to-end inbound is via `tests/test_connectors_discord.py` integration tests that explicitly spin up a stubbed gateway client. **F8 flight-log carry-forward**: add a Deviations entry naming this gap and pointing to L11.
- **Listener idle-eviction concern**: the pool's TTL-based reaper (`_pool.py:_reap_idle`) evicts entries idle for 30+ minutes. A listener entry that sees no inbound traffic could be evicted, killing the gateway connection. **Out of L4 scope** — flagged in F8 carry-forward to L11; mitigation candidates (exempt listener entries from idle eviction; have the listener heartbeat last_activity) are F10 hardening if HAT surfaces the issue.
- **`message.author.roles` not present**: for DMs or webhook messages, `author` may not be a `Member` instance (only `User`). `getattr(author, "roles", [])` returns empty list. Test pins.

## Files Affected

- `the_one/connectors/_discord_translate.py` (NEW) — pure-function translation helper
- `the_one/connectors/_discord.py` — `normalize_session_key` body + `on_message` registration in `connect`
- `the_one/agent/factory.py` — `set_factory()` / `get_factory()` module-level accessor
- `the_one/interfaces/web/app.py` — lifespan startup calls `set_factory(...)` after constructing the factory
- `tests/test_connectors_discord_translate.py` (NEW) — pure-function tests
- `tests/test_connectors_discord.py` — extended with on_message integration tests + normalize_session_key test
- `tests/test_agent_factory.py` (or wherever AgentFactory tests live) — extended with `set_factory()`/`get_factory()` round-trip tests
- `the_one/agents.md` — Connector subsystem section: `get_factory()` module-accessor convention paragraph

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit — wait for flight-level review

## Citation Audit

Citations verified at leg-design time:
- `the_one/connectors/base.py:39-81` — InboundEnvelope dataclass — **OK**
- `the_one/connectors/base.py:96-114` — SessionKey dataclass — **OK**
- `the_one/connectors/_stub.py:200-207` — StubPlugin.normalize_session_key precedent — **OK**
- `the_one/connectors/_inbound.py:156+` — dispatch_inbound entry — **OK**
- `the_one/connectors/_session.py:141` — plugin.normalize_session_key consult site — **OK**
- `the_one/connectors/_commands.py:_parse_command` — pure-function module precedent — **OK**

6 citations verified.
