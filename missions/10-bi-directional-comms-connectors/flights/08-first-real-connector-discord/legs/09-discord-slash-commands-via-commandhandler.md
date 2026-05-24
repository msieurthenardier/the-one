# Leg: discord-slash-commands-via-commandhandler

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Implement `DiscordPlugin.handle_command(envelope, command_name, args) -> CommandResponse | None` so DiscordPlugin structurally satisfies the F7 `CommandHandler` Protocol in addition to `ConnectorPlugin`. Per-guild idempotent (PUT-style replace; NEVER append) registration of the 6 v1 commands (`/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help`) via Discord's Interactions API during `DiscordPlugin.connect` post-READY. Wire `on_interaction` event handler that translates a Discord `Interaction` (slash-command invocation) into an `InboundEnvelope` with `text="/<command> <args>"` and routes it through the same `dispatch_inbound` path as `on_message`. The L1-wired `getattr(plugin, "handle_command", None)` consult site in `_inbound.py` step 11 fires the plugin's handler; the plugin returns `None` to fall through to the built-in dispatcher (the v1 vocabulary is shared) OR returns a `CommandResponse` to customize the response (e.g. use Discord's ephemeral feature so only the invoking peer sees `/help` output).

## Context

L9 of F8. Per flight Design Decisions:

- **Per-guild registration (PUT-style replace)**: discord.py 2.4+ exposes `client.tree.sync(guild=discord.Object(id=guild_id))` for guild-scoped slash commands (also `tree.copy_global_to(guild=...)` for hybrid setups). Per-guild registers in ≤5 minutes (Discord-side cache); global registers in up to 1 hour. F8 ships per-guild only — operator-configured guild list. Global registration deferred to F10 hardening.
- **Idempotent on every connect**: each `DiscordPlugin.connect` calls `tree.sync(guild=...)` for each configured guild. `tree.sync` is a PUT — it replaces the guild's command list with whatever `tree` currently holds. NEVER appends. If the operator changes the configured guild list between starts, removed guilds keep their old commands until the next manual cleanup OR until Discord garbage-collects them (90-day stale-command retention). Out of L9 scope.
- **6 v1 commands map directly**: each registers as a Discord application command with name = bare command (without leading slash). Arguments default to `args: str` (single optional string param) — the user types `/talk-to my-agent`. Sub-args parsed by `_parse_command`'s existing whitespace split at the dispatcher.
- **`handle_command` default = None (fall-through)**: for the v1 commands, DiscordPlugin defers to the built-in dispatcher (the response text comes from the F7 v1 implementations). DiscordPlugin's customization is the `ephemeral` flag on `/help` — Discord's UI surfaces ephemeral responses only to the invoking peer, not the whole channel. Specifically: when `command_name == "help"`, DiscordPlugin returns a `CommandResponse` directly with the F7 v1 help text AND a side-channel signal to the dispatcher's outbound path saying "render as ephemeral." But that side-channel doesn't exist — the dispatcher's outbound uses `client.send(target, text)` which is non-ephemeral. **Compromise**: L9 implements `handle_command` returning `None` for all 6 commands (the simpler path); the ephemeral-`/help` behavior is deferred to F10 hardening if HAT surfaces concrete operator desire.
- **`on_interaction` event handler**: discord.py 2.4 fires `on_interaction(interaction)` on slash-command invocation. The handler translates `interaction` → `InboundEnvelope` with `text=f"/{interaction.command.name} {' '.join(interaction.namespace.<arg_name>.split())}"` (the `/` prefix is required for the dispatcher's `_parse_command` to recognize the command). Sends `interaction.response.send_message(content, ephemeral=False)` for the eventual reply — handled by the dispatcher's outbound path; OR (initial L9 implementation): just acknowledge the interaction via `interaction.response.defer()` and let the dispatcher's outbound `client.send` post the reply in the channel.

Key learnings from L1-L8:
- L1 wired the `CommandHandler` Protocol consult into the dispatcher at `_inbound.py` step 11 with `getattr(plugin, "handle_command", None)`. L9 makes DiscordPlugin's `handle_command` reachable from there.
- L4's `on_message` handler is the parallel for L9's `on_interaction` — same dispatcher, same envelope shape, same factory-via-`get_factory()` access pattern.
- L7's gateway smoke test in `doctor` does NOT register slash commands — keep it isolated from L9's `tree.sync` calls.

## Inputs

- `the_one/connectors/_discord.py` (post-L8) — DiscordPlugin has 6 implemented methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`, `is_dm`, `send` on the client). No `handle_command` yet.
- `the_one/connectors/base.py:358-419` — `CommandResponse` dataclass + `CommandHandler` Protocol.
- `the_one/connectors/_inbound.py` step 11 (post-L1) — `getattr(plugin, "handle_command", None)` consult site.
- `the_one/connectors/_commands.py:_parse_command` — text-prefix parser used by the dispatcher's step 11 to extract command_name + args.
- `discord.py 2.4+` SDK: `discord.app_commands.CommandTree`, `tree.sync(guild=...)`, `client.tree`, `on_interaction`, `interaction.command`, `interaction.namespace`, `interaction.response.send_message(..., ephemeral=...)`.
- L1-L8 test suite green (2371 passed).

## Outputs

- `DiscordPlugin.handle_command(envelope, command_name, args) -> CommandResponse | None`:
  - For the 6 v1 commands (`agents`, `talk-to`, `whoami`, `new`, `reset`, `help`): returns `None` (fall-through to F7 built-in dispatcher).
  - For unknown commands: returns `None` (fall-through; the built-in dispatcher will also return None, and step 11 falls to step 12 → `agent.step`).
  - For platform-native customizations (ephemeral `/help`): **deferred to F10 hardening**. L9 returns None for all commands.

- **Tree construction in `DiscordPlugin.connect`** post-`client = discord.Client(intents=...)`:
  - `tree = discord.app_commands.CommandTree(client)` (or set `client.tree` directly).
  - Register 6 commands via `@tree.command(name="agents", description="...")` etc. Each is `async def` taking `interaction: discord.Interaction` and an optional `args: str` parameter.
  - Each command body translates `interaction` → `InboundEnvelope` with `text=f"/{name} {args}"` (default args="" if not provided), gets the factory via `get_factory()`, calls `dispatch_inbound(account.id, envelope, factory=factory)`.
  - **Acknowledge the interaction**: after dispatching, call `await interaction.response.send_message("acknowledged", ephemeral=True)` (or `defer()`) to satisfy Discord's 3-second interaction timeout. The dispatcher's outbound `client.send` posts the actual response in the channel (non-ephemeral); the ephemeral ack is just the Discord-required "we got your slash command" handshake. **OR alternatively**: `interaction.response.defer(ephemeral=True)` and the dispatcher's outbound is what the user sees. Pick whichever satisfies Discord's API without producing duplicate visible messages.

- **`tree.sync(...)` invocation** in `DiscordPlugin.connect` post-READY:
  - Read `account.config.get("guilds", [])` — the operator-configured guild list for command registration.
  - For each guild_id: `await tree.sync(guild=discord.Object(id=int(guild_id)))`.
  - If guild list is empty: skip sync (no guild-scoped commands registered; slash commands won't appear in any guild). Log INFO.
  - Wrap in try/except — sync failure (network blip, guild not found) should NOT prevent the connection from going live. Log WARNING.

- **`on_interaction` handler**: registered alongside `on_message` and `on_ready` in `DiscordPlugin.connect`. Filters non-command interactions (e.g. button presses — not in scope for L9; would just defer/ack). For application commands, the @tree.command decorator already routes — `on_interaction` may not need separate handling for L9.

- **Tests in `tests/test_connectors_discord.py`** — extended with L9 tests:
  - `DiscordPlugin().handle_command(...)` returns None for each of the 6 v1 commands.
  - `DiscordPlugin().handle_command(...)` returns None for unknown commands.
  - `tree.sync(guild=...)` called once per configured guild during connect (mocked).
  - Empty guild list → no sync calls.
  - Sync failure (raises) → connect still proceeds (warning logged).
  - Slash-command invocation translates `interaction` → `InboundEnvelope` with `text="/agents"` (or similar) and calls `dispatch_inbound` (mocked).
  - DiscordPlugin satisfies `isinstance(plugin, CommandHandler)` after L9.

- L1-L8 regression: 2371 → ~2380 (~9 new tests).

## Acceptance Criteria

- [x] **`DiscordPlugin.handle_command(envelope, command_name, args) -> CommandResponse | None`** implemented. Returns None for all commands (v1 + unknown) in L9; ephemeral-customizations deferred to F10. Async signature matches `CommandHandler` Protocol.

- [x] **`isinstance(DiscordPlugin(), CommandHandler)` returns True**. DiscordPlugin now structurally satisfies both `ConnectorPlugin` and `CommandHandler` Protocols.

- [x] **Command tree construction in `DiscordPlugin.connect`**: a `discord.app_commands.CommandTree(client)` is created post-client construction. Six commands are registered via `@tree.command(name=..., description=...)` with names: `agents`, `talk_to` (hyphen-free — Discord's ASCII command-name regex rejects `-`), `whoami`, `new`, `reset`, `help`. Each takes an optional `args: str` parameter (the post-command-name remainder).

- [x] **Per-guild `tree.sync(guild=...)`** called for each guild in `account.config.get("guilds", [])` after the on_ready event fires. Logs INFO on empty/absent; WARNING on failure (doesn't propagate). Empty list → skip silently (info log "no guilds configured for slash command sync").

- [x] **Slash command body** translates `interaction → InboundEnvelope` (with `text=f"/{name} {args}"`, `peer_id=str(interaction.user.id)`, `peer_name=interaction.user.display_name`, `channel_id=str(interaction.channel_id)`, etc.) and calls `dispatch_inbound(account.id, envelope, factory=get_factory())`. Acknowledges via `interaction.response.defer(ephemeral=True)` to satisfy Discord's 3-second timeout.

- [x] **Tests in `tests/test_connectors_discord.py`** — 13 new L9 tests (above the 8-minimum) covering: handle_command returns None for each of 6 commands + hyphenated `talk-to`; handle_command returns None for unknown; tree.sync called once per guild; empty guild list = no sync; sync failure = connect still proceeds with warning; isinstance CommandHandler = True; slash command translates interaction → envelope (guild + DM paths); dispatch_inbound called from slash-command body; empty-args canonical form; dispatcher-exception graceful isolation; factory-unavailable warning + return.

- [x] **F1-F7 + L1-L8 regression**: 2371 → **2384** (+13 net = +13 new L9 tests; no regressions).

- [x] **`agents.md` Connector subsystem section** — paragraph "### Slash commands via `CommandHandler` (M10 F8 L9)" added; cites the F10 ephemeral-customization deferral.

## Verification Steps

- `grep -c "async def handle_command" the_one/connectors/_discord.py` — exactly 1.
- `grep -c "tree.sync\|tree.command\|app_commands" the_one/connectors/_discord.py` — at least 3.
- `docker exec the-one python -c "from the_one.connectors._discord import DiscordPlugin; from the_one.connectors.base import CommandHandler; assert isinstance(DiscordPlugin(), CommandHandler); print('OK')"` — prints OK.
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes (2371 → ~2380).

## Implementation Guidance

1. Read discord.py 2.4 docs on `app_commands.CommandTree` and `@tree.command` decorator. Confirm the registration pattern.
2. Build `DiscordPlugin.handle_command` — return None.
3. Extend `DiscordPlugin.connect` (post-L3's connect path) with:
   - Construct `tree = discord.app_commands.CommandTree(client)`.
   - Register 6 commands via `@tree.command(...)` decorators inside connect (the decorator captures `account`, `client`, etc. via closure).
   - After on_ready fires: `await tree.sync(guild=discord.Object(id=int(g)))` for each `g in account.config.get("guilds", [])`.
4. Each slash command body: translate interaction → envelope, call dispatch_inbound, ack via defer.
5. Tests: extend the existing stubbed discord module pattern with `app_commands.CommandTree` mock + interaction fixture.
6. agents.md note.
7. Full suite green.

### Code patterns to follow

- **F7 L1's `CommandHandler` Protocol** — runtime_checkable; structural satisfaction.
- **L4's on_message handler** — parallel shape; envelope construction.
- **`get_factory()` from L4** — used by L9 slash-command bodies the same way as on_message.

## Edge Cases

- **Discord command names can't contain hyphens** (Discord API rejects `talk-to`). Use `talk_to` for the registered name; the dispatcher's text-prefix parser already handles both since it's whitespace-split. The L4 on_message handler also handles `/talk-to` via the existing parser. Document at implementation.
- **`account.config.get("guilds", [])` is ABSENT vs `[]`**: both skip the sync. Treat as equivalent.
- **`tree.sync` raises `discord.errors.Forbidden`** (bot lacks `applications.commands` scope): warning logged; connect proceeds; slash commands won't appear in that guild. Test pins.
- **`interaction.response` already acknowledged elsewhere**: shouldn't happen in our flow but defensive — wrap in try/except, log.
- **Slash command invoked from DM channel** (when Discord's permissions allow): `interaction.guild_id` is None; envelope.raw["guild_id"] is None; envelope.raw["is_dm"] is True. The dispatcher's L6 `is_dm` consult sees True and behaves correctly.

## Files Affected

- `the_one/connectors/_discord.py` — `handle_command` + tree construction + slash command registration + on_interaction (if needed) + tree.sync in connect post-READY
- `tests/test_connectors_discord.py` — L9 tests (~8+)
- `the_one/agents.md` — Connector subsystem L9 slash-command paragraph

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set leg status to `landed`
- [x] Check off L9 in flight.md
- [x] Do NOT commit — wait for flight-level review

## Citation Audit

- `the_one/connectors/base.py:358-419` — CommandResponse + CommandHandler — **OK**
- `the_one/connectors/_inbound.py` step 11 (post-L1) — getattr consult — **OK** (L1 wired)
- `the_one/connectors/_commands.py:_parse_command` — F7 text parser — **OK**
- `discord.py 2.4+` `app_commands.CommandTree` — SDK exists per L2 pin — **OK**

4 citations verified.
