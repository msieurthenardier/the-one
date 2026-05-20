# Flight: First Real Connector — Discord

**Status**: planning
**Mission**: [Bi-directional Communication Connectors](../../mission.md)

## Contributing to Criteria

- [ ] Mission #2 — At least two connector implementations ship in this mission, both built against a single connector-plugin contract; at least one uses a persistent connection. **F8 lands the first real connector (Discord, persistent gateway WebSocket) — the contract-validation half of mission criterion #2.**
- [ ] Mission #3 — When an authorized peer sends a message to the bot on the external platform, an agent session resumes (or is created on first contact) and the agent's reply is delivered back on the same platform, in the same conversational location, as the same bot identity. **F8 makes this real for Discord** (F1-F7 already proved it against the stub).
- [ ] Mission #5 — The mapping between external-conversation identity (platform + account + channel + thread + peer) and internal `chat_sessions` row is stable and reversible. **F8 validates the F3 normalization against Discord's snowflake semantics.**
- [ ] Mission #7 — Per-connector-account override of credentials is supported. **F8 exercises this against the Discord bot-token shape; the F1 reserved-key + F2 credentials editor stay verbatim.**
- [ ] Mission #8 — Doctor-style probe accessible from each connector account's Admin detail page verifies the connection lifecycle. **F8 implements the Discord-specific probe (token validity, intent coverage, gateway connect, application summary, allowlist resolution).**
- [ ] Mission #9 — Persistent connections are managed by a per-(agent, connector-account) lifecycle pool with idle-TTL reaping. **F8 is the first real consumer of the F1 pool against a non-stub plugin; validates the reconnect / heartbeat path.**
- [ ] Mission #22 — The command surface is a connector-agnostic primitive — adding a new connector inherits the full command set. **F8 implements `CommandHandler` Protocol on the Discord plugin** — proves the additive extension shape and closes the F7-shipped-but-not-consumed Protocol gap (F7 debrief Critical #1).
- [ ] Mission #29 — Each layer has automated coverage. **F8 adds Discord-specific test coverage** + closes the F7 routing-rules-editor browser-test gap (F7 debrief Important #5).

---

## Pre-Flight

### Objective

Land the first real connector — Discord — and use it to validate the F1-F7 substrate end-to-end against a persistent gateway WebSocket. Implement a `DiscordPlugin` satisfying `ConnectorPlugin` (and additively satisfying `CommandHandler` for native slash-command registration); ship the Discord gateway client with intents, heartbeats, and exponential-backoff reconnect; wire inbound ingestion through the F3 session-key normalizer and F7 dispatcher; wire outbound via the F4 platform-send tool; implement the Discord-specific doctor probe; extend the per-axis allowlist with Discord's role + guild axes; implement the `is_dm` plugin hook and consume it in `_acl.py` to flip the F7-deferred DMs-only fail-closed branch into "permit if envelope is a DM; else deny." As the first "everything must compose" leg, F8 also pulls in every actionable F7 debrief recommendation — either into F8 scope (CommandHandler consult, DM classification, audit-log promise reconciliation, doc/code minors, browser test for routing-rules editor, agents.md convention codification) or as an explicit deferral to F10/routine-maintenance with reasoning.

### Open Questions

- [ ] **Discord SDK choice — `discord.py` vs alternatives**. `discord.py` is the de-facto standard (active maintenance, broad ecosystem, latest version 2.4+ supports Python 3.11+). Alternatives: `hikari` (more typed, smaller community), `nextcord` (`discord.py` fork from a 2021 hiatus, now stale). **Default**: `discord.py` with a pinned version in `pyproject.toml`. Resolve at L2 design — pick the exact version and pin it; document the SDK-pinning rationale in `agents.md` per the M10 mission constraint "Wire-protocol clients use maintained SDKs with pinned versions."
- [ ] **Intent coverage — Message Content intent (privileged)**. Discord requires explicit opt-in for the Message Content intent (operator must enable in the Discord Developer Portal AND the bot's token must request it). Without it, the bot only sees its own DMs + messages it's mentioned in. **F8 default**: require Message Content intent; operator must enable it in the Developer Portal; doctor probe surfaces missing-intent state. Confirm at L2.
- [ ] **Slash-command registration shape**. Discord's Interactions API supports application commands (slash commands) registered globally OR per-guild. Per-guild registers in ≤5 minutes; global registers in up to 1 hour. **F8 default**: register per-guild on first connect (operator-configured guild list); document global as a future opt-in. The six F7 v1 commands (`/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help`) map directly to Discord slash commands via the `CommandHandler` Protocol. Resolve at L9.
- [ ] **`is_dm(envelope)` hook shape — Protocol widening vs `getattr` sentinel**. F6 documented two project conventions: `protocol-widening-for-required-capability` (e.g. `ConnectorClient.send` post-F4) and `optional-plugin-hook-via-getattr-sentinel` (e.g. `resolve` hook in F6). `is_dm` semantically belongs alongside `resolve` — optional, only relevant for plugins that distinguish DMs from channel messages. **Default**: `getattr(plugin, "is_dm", _default_not_dm)` with `_default_not_dm` returning `False` (matches the F7 v1 behavior — no plugin implements it, all stub envelopes are treated as non-DM). DiscordPlugin opts in.
- [ ] **Allowlist axes extension — guilds + roles**. Discord's natural ACL axes are guild + channel + role + user. F1-F6's per-axis allowlist on `connector_accounts.config["allowlist"]` covers `peers` (user) + `channels`. F8 needs to extend with `guilds` and `roles`. **Two options**: (a) extend the existing reserved-key validator with two new axes; (b) introduce a `discord_allowlist` plugin-specific reserved key. **Default**: (a) — the per-axis tri-state framing from F6 generalizes naturally; `guilds` and `roles` are operator-facing concepts that work across "any future connector that has guilds/roles" (Slack has workspaces + roles; Matrix has rooms + power levels). Resolve at L8.
- [ ] **Reconnect budget**. Discord's gateway sends a `RESUMED` event for short disconnects and a fresh `READY` for budget-exceeded reconnects. **Default**: 5 attempts with exponential backoff (1s, 2s, 4s, 8s, 16s), then degrade the account and surface in doctor-probe + Admin status. Reconnects don't bump the per-account session-continuation window. Resolve at L3.
- [ ] **Stub plugin in dev-mode registry — F8 planning decision** (F6 debrief K3 + F7 debrief deferral). Currently the stub is `register_for_test`-only. **Two paths**: (a) register the stub in dev mode (gated on `settings.environment == "dev"`) so the operator can exercise F1-F7 commands end-to-end without a real Discord bot; (b) accept "F8 HAT IS the F1-F7 integration HAT" and drop the stub-in-dev question. **Default**: (a) — having the stub in dev mode (NOT in production) makes future-flight HAT cycles faster and eliminates the F7 L9 step 7 deferral that's accumulated since F6. Pin in `agents.md` as a project convention: "test-only plugins MAY be conditionally registered in dev mode behind a settings gate."

### Design Decisions

**Discord SDK: `discord.py 2.4+`, pinned at flight start, no fallback to alternatives**. `discord.py` is the de-facto standard. Pin in `pyproject.toml` with a `==2.4.x` constraint (pick the exact patch at L2 design — likely whichever is latest at flight start). Rationale: M10 mission constraint ("maintained SDKs with pinned versions"); F1's `mcp` SDK pinning precedent at v9. Trade-off: SDK choice locks F8 to discord.py's API shape; F9 (Slack) will follow the same pattern with `slack-sdk`. Future connectors carry their own pinned SDK; the connector contract sits ON TOP of the SDK.

**`is_dm(envelope) -> bool` plugin hook via `getattr` sentinel**. Mirrors F6's `resolve` hook discovery pattern. `_acl.py` calls `getattr(plugin, "is_dm", _default_not_dm)` at the DMs-only branch. The DMs-only fail-closed branch from F7 L2 (`_acl.py:95`, `:171`) replaces its hardcoded deny with `if plugin.is_dm(envelope): return (True, "")` else current behavior. `_default_not_dm` returns `False` (back-compat: stub envelopes continue to fail the DMs-only check).
- Rationale: optional hooks via `getattr` is the existing project convention (`optional-plugin-hook-via-getattr-sentinel` in `agents.md`); widening `ConnectorPlugin` for a Discord-specific concern would force Slack + future connectors to implement `is_dm` even if they distinguish DMs differently or not at all.
- Trade-off: callers must remember to `getattr` the hook. Mitigation: `_acl.admits_outbound` / `admits_inbound` are the only callers; both centralize the lookup.

**`CommandHandler` Protocol consult site lands in F8 L1 (F7 debrief Critical #1)**. The F7-declared Protocol at `base.py:377-419` ships without a dispatcher consult. F8 L1 adds the consult at `_inbound.py` step 11: before calling `_dispatch_builtin_command`, attempt `plugin_response = await plugin.handle_command(working_envelope, command_name, args)` if `getattr(plugin, "handle_command", None)`. Non-None response emits via system-outbound; None falls through to the built-in handler. Same audit-log treatment (`disposition: "command-intercepted"`).
- Rationale: F7 spec advertises F7 L1 landing this; F7 ship was half-true (type ships, consumption doesn't). Closing in F8 L1 means everything downstream in F8 (slash-command registration; per-plugin command shaping) sits on a fully-wired contract.

**Allowlist axes: extend per-axis tri-state to `guilds` + `roles` on `connector_accounts.config["allowlist"]`**. Adds two axes to the existing `peers` + `channels` shape. Per-axis tri-state semantic from F6 applies verbatim (absent = unrestricted; `[]` = unrestricted on this axis at account scope; non-empty = subset). Per-agent ACL extends with the same axes. Studio Routing Rules editor (F7 L7) does NOT need changes — those are scope-driven, not axis-driven. Studio Allowlist editor (F6 L4) adds two new chip-list rows for guilds + roles.
- Rationale: per-axis-tri-state-override is now n=2 (F6 ACL + F7 routing) → soon n=3. The framing generalizes; F8 evidences it again. Codify as a named project convention in `agents.md` (F7 debrief Important #3) as part of this leg.
- Trade-off: Schema validator gains two new keys → migration concern for existing data. Mitigation: the F6 absent-axis-permits semantic applies; existing accounts without `guilds` / `roles` are unrestricted on those axes by default. F7 HAT3-style legacy-coercion is the precedent for any reads that need it (likely not, since absent is valid).

**Stub plugin registered in dev mode** (F8 planning decision). Add `register_builtin_connectors()` extension at `the_one/connectors/registry.py:147` to register the stub when `settings.environment == "dev"`. Production registration stays empty until F8 L2 lands Discord. Tests continue to use `register_for_test` for isolation.
- Rationale: Eliminates the "no end-to-end HAT path for F1-F7 features" gap (F6 debrief K3, F7 debrief deferral). Operator can drive `/agents`, `/talk-to`, etc. against the stub from a dev-only Studio surface; no real Discord bot needed for F1-F7 regression.
- Trade-off: The stub is now a "supported" registered plugin in dev mode → its surface becomes a soft contract. Mitigation: explicitly call out in `agents.md` that the stub is dev-only and behavior may shift between flights; not a public contract.

**Audit-log "original failed pick" promise — Decision (b): doc fix (F7 debrief Important #4)**. The F7 routing engine emits a SINGLE `RoutingDecision`; only the eventual winner's path lands in `session_metadata["routing"]`. The F7 flight spec promised a chain of skipped candidates. Cheaper fix: revise F7 flight spec language post-hoc + add a clarifying note to the audit-log section of `_routing.py`'s module docstring + `agents.md` Connector subsystem. Defer richer-audit (option (a)) to F10 hardening if operator UX surfaces it as a real concern.
- Rationale: Cheap; matches current shipped behavior; doesn't over-engineer for a hypothetical operator-debugging surface that hasn't been requested. F10 can revisit with concrete UX requirements.
- Trade-off: operators inspecting the audit log can't see "rule X was skipped because its target agent is ACL-denied." Mitigation: documented; F10 hardening agenda item.

**F7 carry-forward batch — single doc-and-codification leg (F8 L1)**. Combines: CommandHandler consult wiring, audit-log promise reconciliation, agents.md codifications (HAT-driven contract-flip discipline + per-axis-tri-state-override convention), three minor doc fixes (`_handle_whoami` semantic, pool-acquire branches comment, `_VALID_ROUTING_SCOPES` export), and the F7 spec-text class-name typo fix.
- Rationale: Each individually is small; bundling into one leg follows the F8-carry-forward-bundle precedent from F7 L8. All share the same surface (connector subsystem + agents.md). Genuinely orthogonal to the Discord work — could land first OR alongside.
- Trade-off: Small risk that bundling delays one item if another slips. Mitigation: leg is small enough to ship in one cycle.

**Browser test for routing-rules editor (F7 debrief Important #5) — lands in F8 L10**. Routing-rules editor UI behaviors (drag-drop reorder, chip-list multi-value match, default-agent stale-selection preservation, snapshot-after-async-population baseline) currently only HAT-validated. Add a Playwright test using the existing `_activate_access_and_routing_tab` helper from F7 HAT1. NOT bundled into F8 L1 because L10 also covers other UI tests if surfaced.

**Doctor probe parallels M07 MCP inspector shape (F1's mission criterion)**. Discord doctor probe returns `DoctorReport` with: `token-valid`, `intent-coverage` (Message Content, Guild Members), `gateway-connect`, `application-summary` (bot name, app id), `allowlist-resolution` (preflight check the operator's guild/channel IDs against Discord's API). Failure path returns `degraded` or `failed` per F1's `DoctorReport` semantic. Runs WITHOUT dispatching messages to peers.

**HAT scope — full operator-driven Discord end-to-end** (F8 L11). The HAT for F8 is substantial: operator provisions a Discord bot, configures intents in the Developer Portal, registers the connector account in Studio, attaches an agent, sends a message from a Discord client → agent replies → operator inspects the audit log. Multiple iteration risk (token shape mistakes; intent gaps; permission edge cases). Plan for it: 3-5 HAT iterations.

### Prerequisites

- [ ] F7 merged to main (verified: commit `dfff8ac flight/07: multi-agent routing and platform-side command surface (#67)`)
- [ ] `_acl.py` DMs-only fail-closed branches at `:95` and `:171` (F7 L2; F8 L6 replaces)
- [ ] `CommandHandler` Protocol declared at `base.py:377-419` (F7 L1; F8 L1 wires consult)
- [ ] `register_builtin_connectors` extension point at `registry.py:147` (F1)
- [ ] `ConnectorAccount.config["allowlist"]` reserved-key validator (F6 L1b; F8 L8 extends with `guilds` + `roles`)
- [ ] F4 platform-send tool (already-working outbound path; F8 reuses)
- [ ] F3 session-key normalizer (`_session.normalize_session_key`; F8's Discord plugin's `normalize_session_key` returns the F3 `SessionKey` shape)
- [ ] F7 routing engine + 12-step dispatcher (F8 plugs in via `CommandHandler` consult and via the existing inbound path)
- [ ] No existing `DiscordPlugin`, `discord.py` import, or `_discord` module in the codebase (grep verified)
- [ ] No prior real-platform connector against the F1 contract (F8 is the validator)

### Pre-Flight Checklist

- [ ] All open questions resolved (7 questions; resolve at per-leg design)
- [ ] Design decisions documented (9 decisions)
- [ ] Prerequisites verified against current code
- [ ] Validation approach defined (per-leg unit tests + L11 HAT + L10 browser test)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

F8 is **the F7-carry-forward bundle first, the Discord plugin foundation second, the gateway client third, the inbound/outbound integrations fourth-and-fifth, the DM-classification hook sixth, the doctor probe seventh, the allowlist axes eighth, the slash commands ninth, the browser test tenth, the HAT eleventh**:

1. **F7 carry-forward bundle** (L1). Wire `CommandHandler` consult into `_inbound.py` step 11. Reconcile F7 audit-log "original failed pick" promise via doc-fix. Codify HAT-driven contract-flip migration discipline + per-axis-tri-state-override convention in `agents.md`. Fix three minor docs (`_handle_whoami` same-turn semantic; pool-acquire branches comment; `_VALID_ROUTING_SCOPES` export). Correct the F7 flight-spec class-name typo (`AgentConfigRepository` → `SQLiteAgentStore`). Stub plugin registered in dev mode behind `settings.environment` gate.

2. **Discord plugin foundation** (L2). Pin `discord.py` in `pyproject.toml`. New module `the_one/connectors/_discord.py` with `DiscordPlugin` class skeleton satisfying `ConnectorPlugin` Protocol (4 methods: `connect`, `disconnect`, `doctor`, `normalize_session_key`). Register in `register_builtin_connectors()` at `registry.py:147`. No gateway logic yet — just the type-level surface.

3. **Discord gateway client** (L3). `DiscordClient(ConnectorClient)` implementing `is_alive` + `send`. Wraps a `discord.Client` instance from the SDK. Connection lifecycle: open → `READY` → emit a `ConnectorReady` (or just transition the pool's `last_activity`); heartbeat handled by SDK; reconnect with 5-attempt exponential backoff (1s/2s/4s/8s/16s); presence set to operator-configurable (default: "Watching agent traffic").

4. **Discord inbound ingestion** (L4). `discord.Client.event(on_message)` translates the Discord `Message` into an `InboundEnvelope` (via a `_translate_discord_message_to_envelope` helper). The dispatcher (`_inbound.dispatch_inbound`) is called with `(account_id, envelope, factory=...)`. F3's `normalize_session_key` consumes the envelope's `channel_id` / `thread_id` / `peer_id`. End-to-end inbound through the F7 12-step dispatcher.

5. **Discord outbound adapter** (L5). `DiscordClient.send(target, content)` wraps `discord.TextChannel.send(content)` (or `Thread.send` if `target.thread_id` is set). Returns `SendResult` with the Discord message id. The F4 platform-send tool already drives outbound; L5 just provides the client-side concrete implementation. No new tool registration.

6. **DM classification hook** (L6). `DiscordPlugin.is_dm(envelope) -> bool` returns `envelope.raw["is_dm"]` (set in L4's `_translate_discord_message_to_envelope` based on `message.channel.type == discord.ChannelType.private`). `_acl.py:95` and `:171` consume via `getattr(plugin, "is_dm", _default_not_dm)`; the fail-closed deny becomes "permit if is_dm; else deny." Tests: stub plugin behavior unchanged (no `is_dm` method); Discord plugin admits DMs through the DMs-only ACL branch.

7. **Discord doctor probe** (L7). `DiscordPlugin.doctor(account, encryptor)` performs: (a) decrypt token; (b) HTTP GET against `https://discord.com/api/v10/users/@me` with `Authorization: Bot <token>` → if 401, return `failed`; (c) parse intents from the bot's application info → check for Message Content + Guild Members; (d) gateway-connect smoke test (open + close); (e) allowlist resolution — for each guild in `config["allowlist"]["guilds"]`, GET `/api/v10/guilds/{id}` and verify the bot is a member. Returns `DoctorReport` with status + per-check details in the M07 inspector shape.

8. **Allowlist axes extension** (L8). Extend `_validate_config_reserved_keys` to accept `guilds` + `roles` axes on `allowlist`. Per-axis tri-state semantic per existing pattern. Extend `_acl.admits_inbound` / `admits_outbound` with the same axes (guild check + role check; both per-account-scope and per-agent). Extend `AgentConfig.connector_acls` inner-dict validator to accept the four-key shape `{peers, channels, guilds, roles}`. Extend the Studio Allowlist editor (F6 L4) with two new chip-list rows.

9. **Slash command registration via CommandHandler** (L9). `DiscordPlugin` implements `async def handle_command(envelope, command_name, args) -> CommandResponse | None`. On `READY`, the plugin registers the 6 v1 commands as Discord application commands (per-guild for the configured guild list). Discord interactions arrive as `on_interaction` events → translated to `InboundEnvelope` with `text="/agents"` etc. → dispatcher's step 11 calls `plugin.handle_command(...)` → DiscordPlugin handles natively (e.g. uses Discord's ephemeral-response feature for `/help`). The L1-wired consult path means F8's slash-command UX layers on top of the existing built-in command behavior.

10. **Browser test for routing-rules editor** (L10) — F7 debrief carry-forward. Playwright test using the `_activate_access_and_routing_tab` helper from F7 HAT1. Cases: add rule, fill chips with multiple values, drag-reorder, save, reload, baseline-not-dirty. Validates F7 L7's HAT-only-verified UI behaviors against regression.

11. **HAT** (L11). Operator-driven end-to-end with a real Discord bot. Steps: provision bot in Discord Developer Portal (token + intents); register connector account in Studio Admin; attach agent in Studio Agent editor; send a message from a Discord client; verify agent reply lands in the right channel; inspect audit log; exercise `/agents`, `/talk-to`, `/whoami`, `/new`, `/help` slash commands.

**Key non-modifications**:

- Agent loop (`agent/core.py`, `agent/factory.py`) — unchanged. F8 is connector-only.
- `dispatch_inbound`'s 12-step composition — unchanged structurally; L1 adds a sub-step inside step 11.
- F3 session-key normalizer — unchanged; consumed.
- F4 platform-send tool — unchanged; consumed.
- F6 resolver hook (`Permit` / `NeedsPairing` / `Deny`) — unchanged; consumed.
- F7 routing engine — unchanged; consumed.
- F7 routing audit-log shape — unchanged.
- Schema migrations — none. Allowlist axes extension rides on `config["allowlist"]` JSON; no SQL.
- `RoutingDecision` dataclass — unchanged.
- F6 outbound reason strings — preserved byte-identically by the existing exact-equality tests.

### Checkpoints

- [ ] `CommandHandler` consult site landed at `_inbound.py` step 11; HAT-discipline + per-axis-tri-state codification in `agents.md`; minor doc fixes shipped; stub registered in dev mode
- [ ] `DiscordPlugin` skeleton + SDK pin landed; satisfies `ConnectorPlugin` Protocol via `isinstance`; registered in `register_builtin_connectors()`
- [ ] Gateway client connects, heartbeats, reconnects through transient drops; degrades on budget exceeded
- [ ] Inbound `on_message` end-to-end through dispatcher; `chat_sessions` row created on first contact; reuse path on subsequent inbounds
- [ ] Outbound via `send_to_platform_channel` tool delivers messages to Discord; `SendResult` carries the message id
- [ ] `is_dm` hook wired; DMs-only ACL branch flips to "permit if DM; else deny"; tests pin both paths
- [ ] Doctor probe returns `DoctorReport` for all five checks; failure paths render in Studio inspector
- [ ] Allowlist `guilds` + `roles` axes validated; Studio editor renders the new chip-lists; ACL admission consults them
- [ ] Slash-command registration via `CommandHandler`; 6 v1 commands appear in Discord client; per-guild registration confirmed
- [ ] Browser test for routing-rules editor passes
- [ ] HAT passes against a real Discord bot

### Adaptation Criteria

**Divert if**:

- `discord.py` 2.4+ has a breaking API change that materially complicates L3's gateway client. Mitigation: pin to an earlier 2.x release; document the pin rationale.
- The Message Content intent is sufficiently gated by Discord (operator can't enable it) that F8 must ship in a degraded mode. Mitigation: doctor probe surfaces the gap; F8 documents the operator-side enablement steps.
- The slash-command registration latency (5 minutes per-guild; up to 1 hour global) makes L9 HAT iteration painful. Mitigation: ship per-guild only in F8; document global as future opt-in.
- Discord's gateway reconnect semantics differ from the F1 pool's reconnect model in a way that materially complicates L3. Mitigation: extend the pool's reconnect-budget knob (already present per `_pool.py` docstring) rather than fight the SDK.
- Allowlist axes extension (L8) surfaces a Pydantic-shape conflict with the existing F6 reserved-key validator. Mitigation: split into 8a (validator extension) + 8b (consumer updates).

**Acceptable variations**:

- L2 may pick a specific `discord.py` patch version different from "latest at flight start" — record the rationale.
- L3 may pick a reconnect-budget schedule different from 1s/2s/4s/8s/16s.
- L4 may decide that `envelope.raw` carries Discord-specific fields beyond `is_dm` (member info, attachments, etc.); F8 documents what fields land in `raw`.
- L7 doctor probe may add Discord-specific checks beyond the five listed (e.g. rate-limit header inspection).
- L9 may decide to ship a SUBSET of the 6 commands as Discord slash commands and document which ones fall through to the built-in text-prefix handler. The default is "all 6 as slash commands."

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `f7-carry-forward-bundle` (1) — `CommandHandler` Protocol dispatcher consult; F7 audit-log doc reconciliation; agents.md codification of HAT-driven contract-flip discipline + per-axis-tri-state-override; three minor doc fixes (`_handle_whoami`, pool-acquire branches, `_VALID_ROUTING_SCOPES` export); F7-spec class-name typo correction; stub plugin registered in dev mode behind `settings.environment` gate
- [ ] `discord-plugin-foundation` (2) — `discord.py` SDK pin; new module `connectors/_discord.py`; `DiscordPlugin` class skeleton satisfying `ConnectorPlugin`; register in `register_builtin_connectors`; tests pin Protocol satisfaction
- [ ] `discord-gateway-client` (3) — `DiscordClient(ConnectorClient)` with `connect`/`disconnect`/`is_alive`; intents wiring; exponential-backoff reconnect; presence configuration
- [ ] `discord-inbound-ingestion` (4) — `on_message` event handler; `_translate_discord_message_to_envelope` helper; end-to-end dispatcher integration; tests against a recorded fixture
- [ ] `discord-outbound-adapter` (5) — `DiscordClient.send` implementation against `discord.TextChannel.send` / `Thread.send`; F4 platform-send tool integration; tests
- [ ] `dm-classification-hook` (6) — `DiscordPlugin.is_dm(envelope)` returns DM-truth from `envelope.raw["is_dm"]`; `_acl.py:95, 171` consume via `getattr(plugin, "is_dm", _default_not_dm)`; DMs-only fail-closed branch flipped; tests pin both paths
- [ ] `discord-doctor-probe` (7) — `DiscordPlugin.doctor` with token-valid + intent-coverage + gateway-connect + application-summary + allowlist-resolution checks; Studio Admin renders the report
- [ ] `allowlist-axes-extension` (8) — extend `_validate_config_reserved_keys` with `guilds` + `roles` axes; extend `_acl.admits_inbound/outbound`; extend `AgentConfig.connector_acls`; extend Studio Allowlist editor; tests
- [ ] `discord-slash-commands-via-commandhandler` (9) — `DiscordPlugin.handle_command` implementation; per-guild registration of 6 v1 commands via Discord Interactions API; native ephemeral-response feature integration
- [ ] `routing-rules-editor-browser-test` (10) — F7 debrief Important #5 carry-forward; Playwright test using `_activate_access_and_routing_tab` helper; covers drag-drop, chip-list, default-agent persistence, baseline-not-dirty
- [ ] `hat-and-alignment` *(11)* — operator-driven end-to-end with a real Discord bot; provision-bot → register-account → attach-agent → send-message → verify-reply → inspect-audit-log → exercise-slash-commands

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing (unit + browser)
- [ ] Documentation updated:
  - [ ] `agents.md` Connector subsystem section adds the `is_dm` hook convention + the dev-mode-conditional-stub-registration pattern
  - [ ] `agents.md` Project Conventions section gains `per-axis-tri-state-override` and `hat-driven-contract-flip-migration-discipline` (F7 debrief carry-forwards)
  - [ ] `connectors/README.md` §X adds a Discord-specific notes section + slash-command registration documentation
  - [ ] `CHANGELOG.md` or release notes (if any) note "Discord connector landed in F8"
- [ ] F7 debrief action items closed (5 critical/important pulled in via L1 + L6 + L8 + L10; 9 deferred items explicitly handed off — F10/routine-maintenance pickup)
- [ ] Mission Open Questions resolved for Discord: SDK choice, intent coverage, slash-command shape, allowlist axes, reconnect budget, stub-in-dev decision

### Verification

The flight achieves its objective when:

1. **Discord plugin landed and registered**: `the_one/connectors/_discord.py:DiscordPlugin` satisfies `ConnectorPlugin` via `isinstance`; registered in `register_builtin_connectors`.
2. **Gateway lifecycle**: connect → READY → heartbeat → reconnect-on-transient-drop → degrade-on-budget-exceeded; doctor probe surfaces lifecycle state.
3. **Inbound end-to-end**: a real Discord message lands as an `InboundEnvelope`; F3 normalizes; F7 routing decides; agent.step runs; reply posts back to Discord.
4. **Outbound end-to-end**: agent calls `send_to_platform_channel` → DiscordClient sends → message appears in the Discord channel with the expected content.
5. **DM classification**: `is_dm` hook wired; DM messages permit the DMs-only ACL branch; non-DM messages deny.
6. **Doctor probe**: returns `ok`/`degraded`/`failed` per the five checks; failure renders distinctly in Studio Admin.
7. **Allowlist axes**: operator can configure `guilds` + `roles` lists on a connector account; ACL admission honors both axes; per-agent narrowing applies.
8. **Slash commands**: `/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help` appear in Discord's command picker; invoking them triggers the dispatcher's command-intercept path with `CommandHandler` consult.
9. **Browser test**: routing-rules editor Playwright test passes consistently.
10. **HAT pass**: operator confirms end-to-end with a real Discord bot.
11. **No agent-loop changes**: `agent/core.py` + `agent/factory.py` byte-identical to F7 ship.
12. **F1-F7 regression**: all 2262 pre-F8 tests pass byte-identically.

---

## F7 Debrief Carry-Forward — Disposition Table

Per operator instruction "pull in every recommendation":

| F7 Debrief Item | Severity | Disposition in F8 |
|---|---|---|
| Wire `CommandHandler` Protocol consult into dispatcher | **Critical** | **L1 scope** — foundation for L9 slash-command registration |
| Codify HAT-driven contract-flip migration discipline (HAT2→HAT3 lesson) | Important | **L1 scope** — `agents.md` codification |
| Codify per-axis-tri-state-override convention in `agents.md` | Important | **L1 scope** — closes F6 debrief rec #3; n=3 after L8 allowlist axes extension |
| Reconcile DD #8 audit-log "original failed pick" promise vs shipped behavior | Important | **L1 scope (doc fix)** — option (b); richer audit deferred to F10 |
| Add Playwright test for routing-rules editor | Important | **L10 scope** — uses `_activate_access_and_routing_tab` helper from F7 HAT1 |
| Document `_handle_whoami` same-turn semantic | Minor | **L1 scope** — promote from docstring to `connectors/README.md` v1 command vocabulary |
| Document pool-acquire branches not sharing state | Minor | **L1 scope** — single-line comment at `_inbound.py` step 10 |
| Export `_VALID_ROUTING_SCOPES` from `db/models.py` to `__all__` | Minor | **L1 scope** — Studio Routing Rules editor can import the enum |
| Correct `AgentConfigRepository` → `SQLiteAgentStore` typo in F7 spec | Cosmetic | **L1 scope** — flight-md correction |
| Keyboard-fallback for drag-reorder in routing-rules editor | Minor | **Deferred to F10 / routine-maintenance** — accessibility regression, not Discord-critical |
| F10 audit-log inspector (Studio surface for `session_metadata["routing"]`) | Important for operator UX | **Deferred to F10** — explicit handoff; F7 HAT step 6 accepted unit-test coverage; not Discord-critical |
| F8/F9 DM-classification consult | F8 prerequisite | **L6 scope** — `is_dm` hook + `_acl.py` consumption |
| Resolve stub-plugin-not-in-production-registry | F8 planning decision | **Resolved at F8 planning** — dev-mode conditional registration; pinned in Design Decisions |
| Dispatcher decomposition (current 12 steps / ~450 LOC) | F10 hardening | **Deferred to F10** — explicit handoff; revisit at 15+ steps |

**Summary**: 9 of 14 items absorbed into F8 scope (across L1, L6, L8, L10); 5 explicitly deferred to F10 or routine-maintenance with documented rationale. Zero items dropped silently.
