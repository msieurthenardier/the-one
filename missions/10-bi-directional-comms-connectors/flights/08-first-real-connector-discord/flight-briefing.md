# Flight Briefing: First Real Connector — Discord

**Date**: 2026-05-20
**Flight**: [First Real Connector — Discord](flight.md)
**Status**: Flight is ready for execution

## Mission Context

M10 lands bi-directional communication connectors — agents reachable on the platforms the operator already uses. F1-F7 shipped the substrate (plugin contract, lifecycle pool, encrypted persistence, admin surface, session model + visibility layers, platform-send tool, Chat UI unified history, pairing + per-agent ACLs, multi-agent routing + command surface). F8 lands the **first real connector** — Discord — and uses it to validate the substrate end-to-end against a persistent gateway WebSocket. F9 ships a second connector that re-uses every abstraction F1-F8 exercises, proving the contract is not accidentally Discord-shaped.

## Objective

Implement `DiscordPlugin` satisfying `ConnectorPlugin` (and additively `CommandHandler`); ship the Discord gateway client with intents, heartbeats, exponential-backoff reconnect; wire inbound through F3's session-key normalizer + F7's 12-step dispatcher; wire outbound via F4's platform-send tool; implement the Discord doctor probe; extend the per-axis allowlist with guild + role axes; implement the `is_dm` plugin hook and flip F7's DMs-only fail-closed branch into "permit if DM, else deny." Also pull in every F7 debrief recommendation — 9 absorbed into F8 scope, 5 explicitly deferred.

## Key Decisions

- **`discord.py 2.4.x` SDK pin** in `pyproject.toml` (M10 mission constraint "maintained SDKs with pinned versions"; M07 `mcp` SDK precedent).
- **`is_dm(envelope) -> bool` hook via `getattr` sentinel** (mirrors F6's `resolve` hook discovery pattern); `_default_not_dm` returns `False` (back-compat).
- **`CommandHandler` consult site lands in L1** (closes F7 Critical #1 gap before F8's slash-command work depends on it).
- **Allowlist axes extended per-axis tri-state to `guilds` + `roles`** on `connector_accounts.config["allowlist"]`. Per-agent ACL extends with same axes.
- **Stub plugin stays test-only — NOT registered in any production code path** (dev-mode-stub rejected per `_stub.py:18-19` invariant).
- **v19 schema migration lands in L2** — `CHECK (type IN ('discord', 'stub'))` on `connector_accounts.type` via table-rename ceremony. CHECK set derived from `CONNECTOR_TYPES` via `_CONNECTOR_TYPES_SQL` projection. `'stub'` included per M07 `'mock'`-in-`PROVIDER_TYPES` precedent (69 test sites use it; `_stub.py` invariant remains the production-purity enforcer).
- **Layers 1-6 of the 8-layer connector-type extension checklist bundle into L2.**
- **Audit-log "original failed pick" promise** reconciled via doc fix in L1 (richer audit deferred to F10).
- **F7 carry-forward batch in L1** — single doc-and-codification leg.
- **Browser test for routing-rules editor lands in L10** (F7 debrief Important #5 carry-forward).
- **HAT scope** — full operator-driven Discord end-to-end in L11; plan for 3-5 iterations.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| `discord.py 2.4+` breaking API change complicates L3's gateway client | Pin to an earlier 2.x release; document rationale |
| Message Content intent gated by Discord such that operator can't enable | Doctor probe surfaces the gap; document operator-side enablement steps |
| Slash-command registration latency (5 min per-guild) makes L9 HAT painful | Ship per-guild only; document global as future opt-in |
| Discord gateway reconnect semantics conflict with pool model | Reconnect lives inside `DiscordClient`, not the pool; pool sees only `is_alive() == False` and respawns the worker. If irreconcilable, fall back to a thinner client and drive reconnect explicitly |
| HAT surfaces `session_metadata["audit"]` race or `config.allowlist.peers` race (F6 F10-candidates) | Adaptation Criteria divert clause — transactional fix in F8 if HAT reproduces; don't defer to F10 |
| L2 Literal narrowing breaks 69 test sites instantiating `type="stub"` | `'stub'` included in `CONNECTOR_TYPES` per operator sign-off; tests continue to work |
| Allowlist axes extension surfaces Pydantic-shape conflict with F6 reserved-key validator | Split into L8a (validator extension) + L8b (consumer updates) |
| L1 bundle has 8 surfaces; one slipping could delay the whole leg | Each surface independently revertible; leg is still sub-day total |

## Legs Overview

1. `f7-carry-forward-bundle` — `CommandHandler` Protocol dispatcher consult + step-11 docstring rewrite + audit-log doc reconciliation + agents.md codification + 3 minor doc fixes + F6 pairing-prefix whitespace tests. **Sub-day, ~8 surfaces.**
2. `discord-plugin-foundation-and-type-registration` — 8-layer checklist (layers 1-6) + v19 CHECK migration + SDK pin + `DiscordPlugin` skeleton + test seed-data updates. **Sub-day.**
3. `discord-gateway-client` — `DiscordClient(ConnectorClient)` + intents + 5-attempt exponential-backoff reconnect + presence. **Half-day.**
4. `discord-inbound-ingestion` — `on_message` handler + `_translate_discord_message_to_envelope` helper in pure-function module + end-to-end dispatcher integration. **Half-day.**
5. `discord-outbound-adapter` — `DiscordClient.send` against `TextChannel.send` / `Thread.send` + F4 platform-send tool integration. **Quarter-day.**
6. `dm-classification-hook` — `DiscordPlugin.is_dm(envelope)` + `_acl.py:95, 171` consume via `getattr`; DMs-only fail-closed branch flipped. **Quarter-day.**
7. `discord-doctor-probe` — `DiscordPlugin.doctor` with 5 checks (token, intents, gateway-connect, app-summary, allowlist-resolution); passes live `encryptor` reference. **Half-day.**
8. `allowlist-axes-extension` — `_validate_config_reserved_keys` + `_acl.admits_inbound/outbound` + `AgentConfig.connector_acls` + Studio editor chip-lists + F6 stale-Enable-toggle cleanup at `editor.js:658, 1361`. **Half-day.**
9. `discord-slash-commands-via-commandhandler` — `DiscordPlugin.handle_command` + per-guild idempotent registration of 6 v1 commands + native ephemeral-response. **Half-day.**
10. `routing-rules-editor-browser-test` — F7 debrief Important #5 carry-forward; Playwright test using `_activate_access_and_routing_tab` helper. **Quarter-day.**
11. `hat-and-alignment` *(optional)* — operator-driven end-to-end with real Discord bot; 3-5 iterations expected.

## Environment Requirements

- **Development environment**: existing the-one dev environment (Docker container or local Python 3.11+).
- **Runtime**: outbound network access to Discord Gateway + REST. No inbound port exposure required.
- **External accounts** (for HAT): operator MUST have a Discord application + bot user with **Message Content** intent and **Guild Members** intent enabled in the Developer Portal. Bot must be invited to at least one guild the operator controls.
- **Tooling**: no new system dependencies. `discord.py 2.4.x` added to `pyproject.toml` in L2.

## Success Criteria

1. `DiscordPlugin` satisfies `ConnectorPlugin` via `isinstance`; registered in `register_builtin_connectors`.
2. Gateway lifecycle: connect → READY → heartbeat → reconnect → degrade-on-budget-exceeded; doctor probe surfaces lifecycle state.
3. A real Discord message lands as `InboundEnvelope`; F3 normalizes; F7 routing decides; `agent.step` runs; reply posts back to Discord.
4. Agent calls `send_to_platform_channel` → DiscordClient sends → message appears in Discord channel.
5. `is_dm` hook wired; DMs permit the DMs-only ACL branch; non-DMs deny.
6. Doctor probe returns `ok`/`degraded`/`failed` per 5 checks; failure renders distinctly in Studio Admin.
7. Operator configures `guilds` + `roles` lists; ACL admission honors both axes; per-agent narrowing applies.
8. `/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help` appear in Discord's command picker.
9. Routing-rules editor Playwright test passes consistently.
10. HAT pass against a real Discord bot.
11. **No agent-loop changes** — `agent/core.py` + `agent/factory.py` byte-identical to F7 ship.
12. F1-F7 regression: all pre-F8 tests pass (byte-identical except for the small set updated to use `'discord'` type).
