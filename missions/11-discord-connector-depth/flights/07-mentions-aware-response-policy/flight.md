# Flight: Mentions-Aware Response Policy

**Status**: in-flight
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] **#12** — Mentions-aware response policy implemented as a new pre-step in the inbound dispatcher; `@mention` → auto-respond, otherwise inference decides; configurable per (agent, channel) with `mentioned-only` / `always-listening` modes; composes cleanly with F7 routing and F8 auto-relay
- [ ] **#13** — Peer-name attribution end-to-end (gateway → dispatcher → session → Chat UI → LLM payload); closes F6 Rec #4 (LLM-side projection deferred from F6 L1) by serializing `peer_name` into provider payloads

---

## Pre-Flight

### Objective

Stop the bot from being chatty. In a busy multi-user channel today the bot runs `agent.step()` on every inbound the dispatcher accepts and auto-relays the reply back to the channel — too eager for daily-driver use. This flight introduces a **policy gate** between the dispatcher's command-intercept fallthrough (step 11) and the per-session lock + `agent.step` block (step 12). The gate engages the agent only when the inbound is unambiguously addressed to it (DM, `/talk_to` override, `@mention`) or when both account-level and per-agent "Always Listen" toggles are ON AND a tight inference LLM call decides — with a strong bias toward silence — that the message warrants a response. Silent turns do NOT persist message content locally, do NOT broadcast to the operator's Chat UI, and the agent's session history stays clean — the bot's "memory" of unobserved channel chatter lives on the platform itself, reachable through new `fetch_*_history` tools when the agent does engage. The Discord connector also closes F6 Rec #4 here: `peer_name` and the new `channel_name` / `channel_id` Message fields are projected into provider payloads via an inline prefix (`[from {peer_name} in #{channel_name}]: <content>`) so the engaged agent can read multi-user context naturally. The end state — verified by an agent-driven Chrome-MCP HAT pass followed by an operator-driven nuance pass — is a Discord-attached agent that participates like a coherent participant rather than an over-eager responder, with the operator able to steer engagement-tendency by typing operator-only directives into the Chat UI ("next time someone says foo, respond with bar") that the inference call observes.

### Open Questions

- [x] **OQ11 (mission)** — Where does the policy gate sit in the 12-step dispatcher? → resolved as Design Decision §1.
- [x] **OQ2 (mission)** — Which LLM runs the inference pre-step? → resolved as Design Decision §2.
- [x] **OQ3 (mission)** — Mode set + granularity? → resolved as Design Decision §3.
- [x] **F6 Rec #4** — `peer_name` LLM-side projection? → resolved as Design Decision §5.
- [x] **Session scoping** — sessions per (channel, thread, DM)? → confirmed already correct in current code; no change needed (see Recon Report).
- [x] **Auto-relay field migration** — keep key + flip semantic vs. replace? → resolved as Design Decision §7.
- [x] **Channel-context tools shape** — one tool with scope arg vs. three separate fetch tools? → resolved as Design Decision §10.
- [x] **Per-agent toggle storage shape** — extend `connector_acls` vs. new field vs. generic policy bucket? → resolved as Design Decision §8 (Architect-finalized).
- [x] **HAT shape** — agent-driven vs. operator-driven vs. both? → resolved as Design Decision §12.

### Design Decisions

**1. Policy gate sits between step 11 (command-intercept fallthrough) and step 12 (per-session lock + `agent.step`).**

- **Rationale**: The gate fires AFTER the routing engine has picked an agent (step 7) and AFTER command-intercept has had its chance (step 11), but BEFORE the per-session lock acquires and `agent.step` runs. This means non-engagement is also non-context — the inbound never lands in `agent.messages` and never enters the agent's working history. Mirrors how humans skim a busy channel.
- **Trade-off**: The agent has zero memory of unobserved turns. The new `fetch_*_history` tools and the inline channel-context projection (DD §5) compensate by giving the engaged agent platform-side context when it actually engages.

**Decision tree** (in order; first match wins):

```
1. envelope.raw["is_dm"] is True?              → engage (DMs ignore policy gate)
2. routing_decision.scope == "override"?       → engage (peer's explicit /talk_to bypasses policy)
3. plugin.is_mention(envelope) returns True?   → engage (explicit @mention)
4. account.always_listen == True
   AND agent.connector_always_listen[account_id] == True?
                                                → run inference; engage if "yes"
5. Otherwise                                   → silent
```

DMs are always-respond. Threads follow channel policy (the gate runs on threads the same as on channel messages; the dispatcher's existing `(channel_id, thread_id)` lookup keys threads to their own sessions, but the policy decision is the same shape).

**2. Inference LLM source: project-wide `settings.inference_provider_config_id` (settings-level pointer to an existing `LLMProviderRepository` row); falls back to the routed agent's configured LLM if unset.**

- **Rationale**: The cheap-local-model path is the operator's primary intent ("monitoring entire conversations" needs to be near-free). A single global setting is simpler than per-account configuration; if the operator wants per-account divergence they can split via separate agents/accounts (the same "split, don't config" principle the granularity decision applied).
- **Trade-off**: One pointer means all connector accounts share the same inference LLM. If the operator later wants per-account divergence, F-future work can add an `account.config["inference_provider_config_id"]` override that reads first and falls back to settings.

**3. Two modes, two-level composition (account-level + per-agent), no per-channel override.**

- Modes: `mentioned-only` (default) and `always-listening`. The 4-mode set from the mission OQ3 (always-respond / mentioned-only / inference / never-respond) collapses to these two — there is no "always-respond ignoring mentions" (always-listen is always-with-inference) and there is no "never-respond" (mentioned-only already silences non-mentions; respond-to-mentions is non-negotiable).
- Account toggle (`account.config["always_listen"]`, default False) is the master capability switch. When False, the inference LLM is never called for this account; per-agent toggles are forced off + disabled in UI.
- Per-agent toggle (`AgentConfig.connector_always_listen[account_id]`, default False — Architect-finalized field name and shape in DD §8) gates which attached agents participate in inference engagement when the account toggle is ON.
- **No per-channel override.** Per-channel divergence ("this agent inferences in #ops but mentioned-only in #general") is out of scope for F7. Rationale: privacy reasoning stays simple ("is my bot listening?" → check account toggle; "will this agent respond?" → boolean). More complex logic → spin up another bot or another agent.
- **Trade-off**: The "this channel is busy, that channel is quiet" use case isn't directly addressable. Acceptable for v1; can revisit if operator hits real friction.

**4. The existing `auto_relay_platform_replies` field is removed; auto-relay (agent plaintext → platform when agent engages) becomes invariant.**

- **Rationale**: The F8 L11 auto-relay default-on was a mechanical fallback for "Sonnet 4.7 doesn't reliably call send_to_platform_channel." That contract holds — but it is no longer something the operator should toggle. Engaged turns auto-relay; non-engaged turns are silent (the policy gate took care of "should we send anything"). The old field's True/False values do NOT carry useful info for the new feature.
- **Migration**: Existing accounts have the key with True/False; on first save after F7 lands, the key is dropped from `account.config`. Existing accounts implicitly upgrade to the safe default (`always_listen` absent → defaults False → mentioned-only behavior — less chatty than today, in the right direction for the F7 motivation).
- **Trade-off**: Operators who deliberately set `auto_relay_platform_replies=False` (wanted to use send_to_platform_channel tool explicitly) lose that mode. F7 doesn't preserve it — the mechanical-fallback-vs-tool toggle was never reliable in F8's framing and removing it simplifies the system prompt.

**5. Peer-name + channel-name LLM-side projection via inline prefix at provider-serialize time. Closes F6 Rec #4.**

- New `Message.channel_name: str | None = None` and `Message.channel_id: str | None = None` fields, optional, default None. Codec follows the `message-additive-back-compat-via-emit-when-non-none` convention (n=4+ for this pattern after F7).
- Dispatcher binds `channel_name` and `channel_id` POST-step on `agent.messages[pre_step_len]` the same way F6 L3 binds `peer_name` — uses the lifted `connectors/post_step_metadata.py` module (see DD §6).
- **Provider adapters serialize a Message with peer_name + channel_name by prepending an inline header to the user-role content: `[from {peer_name} in #{channel_name}]: <content>`.** Both fields optional; absent-on-message → no prefix. Serialization site is each provider's `_to_api_message` (or equivalent): `the_one/llm/openai_provider.py:_to_api_message` (line ~247), `the_one/llm/anthropic_provider.py:_to_api_message` (line ~210), `the_one/llm/ollama_provider.py:_to_api_message` (line ~244). **OpenRouter inherits via `OpenAIProvider`** (`the_one/llm/openrouter_provider.py`) — the inherited `_to_api_message` picks up the change automatically; L4 tests must include a parity assertion.
- **Premise revalidation per `cross-subsystem-pattern-premise-revalidation`**: F6 DD §2's provider audit pinned that the adapters project `{role, content}` and `peer_name` cannot leak. F7's projection deliberately changes that — the prefix IS the projection. Audit step: the new provider serialization is opt-in (only fires when `peer_name` or `channel_name` is non-None); legacy non-connector sessions (no peer_name binding) emit byte-identical payloads to today.
- **Trade-off**: The Chat UI rendering may want to either show the prefix in operator-visible-side display (operator sees what the LLM sees — useful for debugging) or strip it from display (operator sees the cleaner "from alice" peer_name field rendering F6 added). UI-side display decision is part of the leg spec (DD: do NOT strip — operator-side parity with LLM input is desirable; the F6 peer-bubble visual treatment continues to render via `Message.peer_name` field, and the prefix is a content-side annotation the operator can see).

**6. Lift the `post-step-dispatcher-message-metadata-binding` mutators to `connectors/post_step_metadata.py`. n=3 threshold met (visibility + peer_name + channel_name/channel_id).**

- Per `agents.md`'s convention citation: "When n=3 is reached, lift the mutators into a shared `connectors/post_step_metadata.py` module that exports each function with a documented composition contract."
- Module exports: `tag_post_step_visibility` (existing), `bind_peer_name` (extracted from F6 L3), `bind_channel_context` (new). Each function documents the Role(s) it touches and the Role(s) it skips so readers can verify non-overlap by inspection. Composition: all three mutators iterate `messages[pre_step_len:]` (or address `pre_step_len + N` directly); none touches pre-existing history; each mutation lives inside the existing `session_locks[session_row.id]` lock and the existing `try` block per the codified pattern.
- **Trade-off**: Touches `the_one/connectors/visibility.py` (move + re-export with deprecation comment) and `the_one/connectors/_inbound.py` (replace inline mutation with module calls). Tests must be moved or updated alongside the function relocation.

**7. New plugin hook `is_mention(envelope) -> bool` via `optional-plugin-hook-via-getattr-sentinel`.**

- **Rationale**: Plugin-agnostic. The substrate dispatcher consults `getattr(plugin, "is_mention", _default_no_mention)`; plugins that don't implement it (the stub, future webhook-driven connectors) fall through to `False`. n=6+ for this convention after F7 (existing: resolve, display_channel, handle_command, is_dm, enumerate_discoverable_entities).
- **Discord implementation**: `def is_mention(self, envelope: InboundEnvelope) -> bool:` reads `envelope.raw["discord_message"].mentions` (list of User/Member); compares each `.id` to the bot's user id (`self._user.id` snapshot captured at READY per F8 L4); returns True if any match.
- **Default fallback**: `def _default_no_mention(envelope: InboundEnvelope) -> bool: return False` lives at `the_one/connectors/_acl.py` alongside `_default_not_dm` (sibling defensive defaults; mirrors the F8 L6 precedent).
- **Trade-off**: Webhook-driven platforms that don't have a mention concept never engage on non-mentions even with always-listen ON (inference still runs; mentions just never short-circuit). Acceptable — the inference call covers all cases.

**8. Per-agent storage: new `AgentConfig.connector_always_listen: dict[str, bool] | None` field. Default None (no entries; all-False semantic). Architect-confirmed: named field, not generic bucket.**

- **Operator's lean**: option 2 (separate field for policy data, not commingled with the ACL list-shaped data); deferred final shape to Architect.
- **Architect cycle-1 confirmation**: ship the named field, mirroring the `connector_acls` precedent at `agent/config.py:246` (per-account dict keyed by `account_id`, distinct from list-shaped ACL data). Validator follows the `connector_acls` validator template at `agent/config.py:251-311`. YAGNI bias from `agents.md` rules out the speculative generic-bucket option until a second per-account policy field surfaces.
- **Schema migration**: new column `connector_always_listen TEXT` on `agents` (JSON-serialized dict). Atomic-leg-pattern: Pydantic field + DB migration + repository codec + `AgentFactory` consumer + ACL editor UI all land in one leg.
- **Validator**: `dict[str, bool] | None`; outer key is `account_id`; inner value is bool. Absent account_id → False (inherit "off" default); explicit False → equivalent to absent; True → only valid when `account.always_listen` is also True (validator can either reject the inconsistency or accept-and-document — the dispatcher's gate composition already handles the False+True case correctly by checking account first; accept-and-document is the lighter discipline).
- **Trade-off**: A new field means another column for routine-maintenance auditing. The generic policy bucket would absorb future fields without new columns but the YAGNI bias wins.

**9. Inference call infrastructure: `the_one/connectors/_inference.py:run_engagement_inference(account, envelope, session_messages, settings, provider_repo, fallback_provider_config_id) -> bool`.**

- **Filtered session history**: takes `session_messages` (full list); filters to `Role.USER` + `Role.ASSISTANT` (with non-empty `content` AND no tool_calls); takes last 20 from the filter result. Tool calls and tool results are dropped (per operator: "the model can be pretty small so it should most definitely not try to read the entire session"). **Operator-tagged turns are prefixed** with `[operator] ` in the filtered projection so the inference LLM can distinguish operator-typed steering from peer messages — operator-typed messages enter `agent.messages` with `visibility="operator"` (F4 L4 + F5 L4 ratify this tagging); the filter projection inspects each Message's visibility and prepends the marker on operator-only USER turns.
- **Provider resolution + error semantics**:
  - Reads `settings.inference_provider_config_id` (new settings field, optional).
  - **Unset** → fall back to the routed agent's LLM (resolved via the fallback_provider_config_id parameter passed from the dispatcher).
  - **Set and resolves successfully** → use that provider.
  - **Set but resolution raises** (provider row deleted, encryptor failure, etc.) → treat as inference-no (silence) and log. Does NOT fall back to the routed agent — operator misconfiguration is surfaced via the audit log's `policy.inference_provider_id: null` + log warning, not papered over (mirrors `agent/factory.py:259-263`'s `ProviderNotFoundError`-propagation precedent inverted to silent-default since this isn't the agent's primary provider).
  - **Fallback (routed-agent) provider misconfigured** → treat as inference-no (silence) with the same safe-default. The routed agent's primary path will surface the provider error separately when an engaged turn tries to run `step()`.
- **Channel name resolution for the prompt template**: the inference call runs BEFORE the post-step binding (which fires only on engagement). Resolution path: (a) look up `envelope.channel_id` in the discoverable-entities cache (F3 L4) for a friendly label; (b) fall back to raw `envelope.channel_id` if the cache lacks a label (cold pool, channel not in cache, non-Discord plugin). Same resolution function L3 will use when binding `Message.channel_name` post-step — single helper, both call sites.
- **Prompt format** (the actual text F7 ships):

```
You are deciding whether an AI agent should respond to a message in a chat conversation.

Recent conversation context (most recent last):
{filtered_session_history_as_turns}

New message from {peer_name} in {channel_name}:
{inbound_text}

Should the agent respond? Respond with exactly one word: "yes" or "no".

STRONG BIAS TOWARD "no". An overly chatty bot is annoying — silence is the default. Only respond "yes" when there is high confidence (beyond a reasonable doubt) that the agent should engage. Pass on borderline cases.

"yes" criteria — at least one must clearly hold:
- The message is unambiguously directed at the agent (by name, implicit reference, or direct question that no human in the conversation has answered)
- The message is a question that the agent's persona is clearly well-suited to answer AND no other participant has answered
- The recent context shows the agent is mid-conversation about this topic
- The operator has explicitly indicated (in operator-only messages tagged visibility="operator") that the agent should engage with this kind of message

When in doubt, "no".
```

- **Output parsing**: response text is lowercased + stripped; first token compared against `"yes"` (engage) / `"no"` (silent). Anything else (the LLM hedged, multi-word response, error) treats as "no" (safe default — silence).
- **Temperature**: 0.0 (deterministic). Max tokens: 10 (forcibly short).
- **Error handling**: any exception during the inference call (LLM down, provider config missing, parsing failed) is logged and treated as "no" — silence is safe. The mechanical fallback discipline applies.
- **Trade-off**: The inference prompt is hand-tuned text; not operator-editable in F7. If the bias proves too strict at HAT, the leg author may iterate the wording at debrief time; that's normal HAT-driven contract refinement.

**13. Silent-turn session-row creation: accept the empty-row cost. Policy gate's silent branch is a terminal return.**

- **Rationale**: Session resolution runs at step 5 (BEFORE the gate at step 11.5). On a silent turn, the session row is created (if not already present) or matched (continuation-window logic). The row gets the routing-audit entry (`disposition="policy-silent"`) but no message body. The `messages` array stays empty (or unchanged from prior engagement).
- **Why accept**: the empty row IS the artifact the audit log points at. Deferring session resolution into the gate's "engaged" branch would leave `session_metadata["routing"]` entries with nowhere to land (no session_id to write against). The empty-row cost is bounded (one row per (channel, thread, DM) the bot has ever seen) and decays via the existing `update_last_inbound` continuation-window mechanism.
- **Terminal-return semantics**: the gate's silent branch (paths 4-fail and 5 of the decision tree in DD §1) **returns from `dispatch_inbound` immediately** after appending the audit entry. Specifically:
  - The session row is NOT lock-acquired (no `async with session_locks[session_row.id]`).
  - `update_last_inbound` is NOT called (silent turns don't extend the continuation window — mirrors F6 Deny / NeedsPairing-failure precedent at step 6).
  - The agent is NOT built; `agent.step` is NOT called.
  - The auto-relay path (step 12 internal) is NOT triggered (it lives inside the engaged branch).
  - The broadcast to WS observers is NOT fired (silent turns don't surface in the Chat UI per DD §3 — privacy invariant).
  - The audit append at `session_metadata["routing"]` IS the only side effect, plus the silent decision logging.
- **Trade-off**: A silent-only channel still accumulates routing audit entries on every inbound. This is the desired observability ("did the bot see this message and decide to stay silent?"). Audit-log size growth is acceptable; F9's audit-log inspector flight handles rendering/pagination.

**10. Channel-context tools: three fetch tools + one list tool, plus two new plugin hooks.**

- **Tools** (all built-in, registered in F7):
  - `fetch_channel_history(channel_id: str, limit: int = 20) -> list[dict]` — fetches recent messages from a channel the bot can see. Each returned dict carries `peer_id`, `peer_name`, `content`, `ts`, `thread_id` (if the message is in a thread).
  - `fetch_thread_history(channel_id: str, thread_id: str, limit: int = 20) -> list[dict]` — same shape but scoped to a thread.
  - `fetch_dm_history(peer_id: str, limit: int = 20) -> list[dict]` — fetches DM history with a specific peer. The plugin internally resolves peer_id → DM channel.
  - `list_visible_channels() -> {peers, channels, groups, roles}` — enumeration of what the bot can see, axis-keyed. Shares the same shape as the F3 L4 `DiscoverableEntities` response (peers/channels/groups/roles) — reuses the existing `enumerate_discoverable_entities` plugin hook to populate.
- **Plugin hooks** (new, on `ConnectorPlugin` Protocol; optional via getattr-sentinel):
  - `fetch_history(client: ConnectorClient, channel_id: str, thread_id: str | None, limit: int) -> list[FetchedMessage]` — substrate-generic; Discord wraps `discord.TextChannel.history()` / `discord.Thread.history()`.
  - `fetch_dm_history(client: ConnectorClient, peer_id: str, limit: int) -> list[FetchedMessage]` — substrate-generic; Discord wraps `discord.User.create_dm().history()`.
  - `list_visible_channels` reuses the existing `enumerate_discoverable_entities` hook (no new hook needed).
- **Account ID resolution**: tools consult the current session's `connector_account_id` via the dispatcher-set `current_chat_session_id` ContextVar (existing F3 plumbing) → look up session row → read `connector_account_id` column → resolve plugin + client via `account_acquire(account_id)`. Three plugin hooks: `fetch_history`, `fetch_dm_history`, `enumerate_discoverable_entities` (existing).
- **Per-agent ACL**: tools respect the existing per-agent connector_acls — the agent can only fetch from channels/peers/etc. its ACL admits. If the agent is denied on a requested channel, the tool returns an empty list with an error sentinel in the dict (`{"error": "agent not permitted to read channel X"}`).
- **Trade-off**: Four new tools = four new schema descriptions that count against the LLM's tool budget. Acceptable — the always-listen experience requires them.

**11. System prompt simplification: drop `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE`; update `_CONNECTOR_AUTO_RELAY_DIRECTIVE`; remove `auto_relay` kwarg from `compose_system_prompt`.**

- Auto-relay is invariant in F7 (DD §4). The remaining directive informs the agent that:
  - Its plaintext replies are auto-delivered to platform peers when it engages.
  - It engages on mentions, DMs, `/talk_to` overrides, or inference-yes turns.
  - Recent channel context not in its session history can be reached via `fetch_*_history` tools.
  - It can see what channels/peers/etc. it has access to via `list_visible_channels`.
- The `send_tool_enabled` kwarg on `compose_system_prompt` remains (other callers compute it for unrelated purposes per the F5 R8 comment), but is no longer consulted in directive selection — the directive is unconditional when `connector_attached=True`.
- **Mechanical-fallback-prompt-truth-pairing**: the new directive accurately describes both the auto-relay invariant AND the policy gate's existence — the agent knows the inference call may have decided to silence non-mentioned messages and that the operator can steer via Chat UI.
- **Trade-off**: Existing tests for the OFF directive's wording will fail. Test cleanup is part of the leg.

**12. HAT shape: two-phase. Agent-driven Chrome-MCP pass FIRST; operator-driven nuance pass SECOND.**

- **Phase 1 (agent-driven)**: The implementing agent uses Chrome MCP (the existing chrome-devtools MCP server registration) to drive a logged-in Discord browser session. It:
  - Sets up a test server fixture (3+ users, 3+ channels, 1 thread, 1 DM channel).
  - Walks the gate decision tree mechanically: post `@mention` → expect response; post non-mention with always-listen OFF → expect silence; post non-mention with always-listen ON + agent ON → expect inference-decided response; etc.
  - Captures observations into a structured report (pass/fail per criterion + screenshots for evidence).
  - Surfaces anomalies + nuance points the agent can't judge ("this looks visually right but does it feel chatty to a human?").
- **Phase 2 (operator-driven)**: The operator walks the same gate criteria using a real Discord client with the agent's report in hand. Confirms the agent's pass/fails; catches nuance the mechanical pass missed (response timing, conversational rhythm, false-positives/negatives in inference judgment).
- **Methodology precedent**: F7 is the first flight to use agent-driven Chrome MCP HAT (F4-F6 used Chrome MCP for in-flight verification but HAT was operator-only). The mission's criterion #11 (durable Chrome-driven HAT script) belongs to F10; F7's Phase-1 work is the precursor — the agent's HAT walk becomes the seed pattern F10 generalizes.
- **Trade-off**: Phase 1 is expensive (Chrome MCP runs are slow); but it catches mechanical issues before operator time is spent. The two-phase pattern is the F4-debrief-validated `HAT-gated-commit ordering` discipline scaled up.

### Prerequisites

- [ ] M11 `agents.md` codifications verified present (M11 Known Issue #1 — checked at recon: all 5 M10-codification candidates + 6 additional ones are in place).
- [ ] F6 landed (PR #74 merged) — `Message.peer_name` field + post-step binding + Chat UI rendering all live.
- [ ] Chrome MCP server registered + chrome-devtools tools available — confirmed via mission Environment Requirements.
- [ ] Discord test guild fixture available — at least 3 users (operator + 2 burners), 3 channels, 1 thread, ability to DM the bot. **Fixture is operator-provided pre-leg** (not created during L12); leg author confirms fixture state at L12 kickoff. If not pre-existing, L12 setup includes a guild-creation step (~30 min operator time).
- [ ] Existing carry-forward debt items audited per `cross-flight-ux-debt-reconciliation` — Recon Report in flight-log.md.

### Pre-Flight Checklist

- [ ] All open questions resolved
- [ ] Design decisions documented
- [ ] Prerequisites verified
- [ ] Validation approach defined (DD §12: two-phase HAT)
- [ ] Legs defined

---

## In-Flight

### Technical Approach

F7 lands in 12 legs organized into four logical groups:

**Group A — Foundation (codifications + module lift + plugin hook)** lays the conventions and substrate the rest of the flight cites. The post-step Message-mutation idiom hits its n=3 trigger and lifts to `connectors/post_step_metadata.py`; the new `is_mention` plugin hook lands per the `optional-plugin-hook-via-getattr-sentinel` convention. One leg.

**Group B — Message + projection (closes F6 Rec #4)** adds `Message.channel_name` + `Message.channel_id` fields with codec back-compat, binds them in the dispatcher's post-step pass using the lifted module, and updates the three provider adapters to serialize peer_name + channel_name into the LLM payload via inline prefix. Three legs (atomic-leg-pattern boundaries: Message + codec is one leg, dispatcher binding is one leg, provider adapters is one leg — the contracts are independent wire-format / runtime / serialization concerns).

**Group C — Policy gate + storage (the behavioral feature)** ships the account-level + per-agent storage migrations (atomic-leg-pattern, one leg each), the inference call infrastructure (one leg, mock-LLM tested), and the dispatcher pre-step that composes them into the decision tree (one leg, all five branches tested). Four legs.

**Group D — Operator surfaces + verification** ships the system prompt simplification, channel-context tools, Studio UI work, and the two-phase HAT. Four legs.

**Order of execution**: Group A first (substrate). Then Group B in order (L2 → L3 → L4) so provider adapter tests can reference the bound Message fields. Then Group C in order (L5 → L6 → L7 → L8 — storage before infrastructure before gate). Then Group D (L9 → L10 → L11 → L12).

**Cross-cutting conventions invoked**: `atomic-leg-pattern` (L5, L6, L2+L3 combined); `optional-plugin-hook-via-getattr-sentinel` (L1, L11); `post-step-dispatcher-message-metadata-binding` (L1, L3); `message-additive-back-compat-via-emit-when-non-none` (L2); `cross-subsystem-pattern-premise-revalidation` (L4 — provider audit shifts from "no leak" to "intentional projection"); `mechanical-fallback-prompt-truth-pairing` (L8, L10 — system prompt + dispatcher gate composition); `cross-flight-ux-debt-reconciliation` (recon phase — see flight-log).

### Checkpoints

- [ ] Group A complete: `connectors/post_step_metadata.py` module published; `is_mention` plugin hook exists on `DiscordPlugin`; new agents.md citations land
- [ ] Group B complete: Provider audit re-validated; OpenAI / Anthropic / Ollama all project peer_name + channel_name; F6 Rec #4 marked closed in F6 debrief
- [ ] Group C complete: Policy gate decision tree exercised end-to-end against stub plugin (unit tests); account.config["always_listen"] persists; AgentConfig.connector_always_listen persists
- [ ] Group D complete: Studio UI surfaces the toggle relabel + per-agent toggle; agent-driven Chrome-MCP HAT report generated; operator-driven nuance pass complete
- [ ] Mission criterion #12 closed-by-F7; mission criterion #13 closed-by-F6 → fully closed by F7 LLM-side projection

### Adaptation Criteria

**Divert if**:
- The inference LLM's bias-toward-silence wording is fundamentally insufficient (HAT shows the bot still chatty even with strict prompt) → revisit the prompt, consider adding a per-account inference-floor heuristic (e.g., require explicit name match for non-mentioned engagement).
- Provider-side projection breaks one of the three adapters in ways that can't be patched in-leg (e.g., Anthropic's content-block shape doesn't accept the inline prefix gracefully) → may need to fall back to a per-provider projection strategy, splitting L4 into sub-legs.
- The Chrome-MCP HAT pass surfaces a structural issue (e.g., Discord's web client gates browser automation differently than expected) → escalate to operator; Phase-2 covers the gap manually for F7; Phase-1 mechanical pattern reconsidered for F10's durable script.
- A leg's scope expansion exceeds 2x the estimated LOC → architect re-review before committing.

**Acceptable variations**:
- The fetch tool descriptions and parameter shapes may iterate during L10 implementation as the agent-UX clarity is verified empirically.
- The Studio UI's exact placement of the per-agent toggle within the agent's Connectors tab may iterate at HAT.

**Scope deferral provision** (per Architect cycle-1 recommendation):
- If Group C (gate behavioral — L5 through L8) extends past 2x estimated LOC OR exceeds the Group A+B time budget by 50%, **defer L11 (Studio UI) and L12 (HAT) into a follow-on flight F7.5** that ships the operator surfaces + HAT. Group A-C alone closes mission criterion #12 mechanically (config can be hand-edited via the existing connector-account config raw-JSON table); the deferred legs polish the operator experience. Flight Director makes the call at the Group C debrief checkpoint.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `codifications-and-post-step-module-lift` — Add `agents.md` citations for the new `optional-plugin-hook-via-getattr-sentinel` site (`is_mention`); lift the post-step Message-mutation mutators to `connectors/post_step_metadata.py` (n=3 trigger met: visibility + peer_name + channel_name/channel_id); migrate existing call sites to import from the new module; add the new `is_mention` plugin hook to `ConnectorPlugin` Protocol (via getattr-sentinel — not Protocol-widening) with `_default_no_mention` fallback at `_acl.py`; Discord plugin implements `is_mention`; tests for both the module lift and the new hook
- [x] `message-channel-context-field-and-codec` — Add `Message.channel_name: str | None` and `Message.channel_id: str | None` fields; codec `emit-when-non-None` encode + back-compat decode (per `message-additive-back-compat-via-emit-when-non-none` convention); update `Message.user(...)` helper to accept kwarg-only `channel_name` + `channel_id`; tests pin the round-trip and the absence-default semantic
- [x] `dispatcher-channel-context-binding` — In `connectors/_inbound.py`'s step 12 try block, after `tag_post_step_visibility` and `bind_peer_name` calls (from the lifted module), call `bind_channel_context(agent.messages, pre_step_len, channel_name=working_envelope.channel_name_resolved, channel_id=working_envelope.channel_id)`. Channel name resolution: Discord plugin's `enumerate_discoverable_entities`-cached label lookup; non-Discord plugins use the channel_id as the name fallback. Tests pin the binding + non-overlap with other post-step mutators
- [x] `provider-side-llm-projection` — Update OpenAI / Anthropic / Ollama provider adapters' `_to_api_message` (or equivalent user-message serialization site) to prepend `[from {peer_name} in #{channel_name}]: ` to the content when peer_name or channel_name is non-None (graceful absence — present only what's set). Files: `the_one/llm/openai_provider.py:_to_api_message:~247`, `the_one/llm/anthropic_provider.py:_to_api_message:~210`, `the_one/llm/ollama_provider.py:_to_api_message:~244`. **OpenRouter inherits via `OpenAIProvider`** — `the_one/llm/openrouter_provider.py` picks up the change automatically; tests include a parity assertion. Provider audit per `cross-subsystem-pattern-premise-revalidation`: F6 DD §2's "no leak" guarantee shifts to "intentional projection." Tests: (a) round-trip with both fields set; (b) round-trip with only peer_name; (c) round-trip with only channel_name; (d) byte-identical legacy payload when both are None; (e) per-provider parity (all three serialize the same content string); (f) OpenRouter inherited serialization parity. Closes M10 mission Bug C / M11 criterion #13's LLM-side gap (F6 Rec #4)
- [x] `account-always-listen-storage-migration` — Atomic-leg-pattern: add `always_listen: bool` to the `ConnectorAccount.config` schema (Pydantic field on the inline config dict via validator); API endpoint accepts the new field on POST/PUT; old `auto_relay_platform_replies` key removed on first save (existing rows reading with the old key continue to work read-only until rewritten); tests for both write paths + the migration semantic. **Surfaces to touch** (per Architect cycle-1 enumeration): Python — `the_one/db/models.py:422-436` validator (replace `auto_relay_platform_replies` validator with `always_listen` validator of the same shape), `the_one/connectors/_inbound.py:730` (auto-relay invariant — drop the config read; auto-relay always-on when engaged branch fires), `the_one/agent/factory.py:329-342` (drop the auto_relay computation entirely along with the kwarg removal in L9). JavaScript — `static/js/areas/studio/connector-account-editor.js:539-564` (toggle render), `:1030-1035` (collect-config), `:1171` (validation snapshot), `:1734-1744` (second merge path — explicitly named so the leg author doesn't miss it).
- [x] `agent-connector-always-listen-storage` — Atomic-leg-pattern: new `AgentConfig.connector_always_listen: dict[str, bool] | None` field (final shape Architect-finalized — alternative: `connector_policies` bucket); schema migration on `agents` table (new column); repository codec; API endpoint accepts the new field; validator (per `agents.md` `field_validator` precedent for `connector_acls`); tests for the round-trip + the absent-account_id → False semantic
- [x] `inference-call-infrastructure` — New `the_one/connectors/_inference.py:run_engagement_inference(...)` per DD §9; new `settings.inference_provider_config_id` field (optional); filtered session-history projection (USER + ASSISTANT-plaintext only, last 20); prompt template per DD §9; provider resolution with fallback; output parsing (lowercase + first-token compare; non-"yes" → False); temperature=0.0, max_tokens=10; error handling (any exception → False); tests with stub provider (yes/no/garbage/raise paths)
- [x] `dispatcher-policy-gate-pre-step` — New step in `connectors/_inbound.py` between step 11's command-intercept fallthrough and step 12's per-session lock. Decision tree per DD §1; terminal-return semantics on silent branches per DD §13. Routing audit shape extension per the agreed `policy` sub-block; new `disposition = "policy-silent"` value. Tests for each branch (DM-engage, override-engage, mention-engage, account-off-silent, agent-off-silent, inference-yes-engage, inference-no-silent, inference-exception-silent — the error-path safe default per DD §9); also tests that the existing `disposition = "stepped"` path is unchanged for mention/DM/override cases, and that silent-branch terminal-return doesn't acquire the session lock or call `update_last_inbound` (mirrors F6 Deny / NeedsPairing-failure precedent)
- [x] `system-prompt-simplification` — Drop `_CONNECTOR_AUTO_RELAY_OFF_DIRECTIVE`; update `_CONNECTOR_AUTO_RELAY_DIRECTIVE` per DD §11 (mentions-aware policy disclosure + channel-context tools mention); remove `auto_relay` kwarg from `compose_system_prompt` (test fix at every call site); keep `send_tool_enabled` kwarg as no-op for back-compat; update Python+JS directive-defaults cross-check (KEEP-IN-SYNC comments per F5 carry-forward); tests
- [x] `channel-context-tools` — Four new built-in tools per DD §10 (`fetch_channel_history`, `fetch_thread_history`, `fetch_dm_history`, `list_visible_channels`); two new plugin hooks via `optional-plugin-hook-via-getattr-sentinel` (`fetch_history`, `fetch_dm_history`); Discord implementations wrap `discord.py` history APIs; per-agent ACL respected; session-context resolution via `current_chat_session_id` ContextVar + session row's `connector_account_id`; tests for each tool (happy path + ACL-denied path + plugin-missing-hook path)
- [x] `studio-ui-policy-toggles` — Connector account editor: relabel existing toggle "Auto-reply to platform messages" → "Always Listen" (account-level capability switch); update help-text + info-icon tooltip; per `field-row-3-column-info-icon-as-sibling` pattern per F5 codification. Agent's Connectors tab: new toggle per attached account ("Always Listen on this connector account"); disabled-state composition (greyed-out when account toggle is OFF); per `field-row-3-column` pattern; uses an event channel (`connector-account-always-listen-changed`) — n=3 for the cross-component CustomEvent pattern, triggers F4 debrief's studio-event-bus lift recommendation (defer the bus lift to routine-maintenance; leg ships the third inline string with TODO citing the lift candidate). Browser tests for both surfaces
- [ ] `uat-and-alignment` — Phase 1 (agent-driven) Chrome-MCP HAT walking the decision tree against a real Discord test guild; structured pass/fail report with screenshots; followed by Phase 2 (operator-driven) where the operator walks the same criteria with the report in hand and surfaces nuance the mechanical pass missed. Iterative HAT round budget: 1-2 rounds for mechanical issues + as-needed rounds for nuance (per F5 debrief's cumulative-debt-vs-single-feature HAT budgeting heuristic — F7 is single-feature so floor of band, but the multi-mode composition surface is wide enough to expect 2-3 rounds)

---

## Post-Flight

### Completion Checklist

- [ ] All 12 legs completed
- [ ] Code merged (PR)
- [ ] Tests passing (Combined ≥ pre-F7 baseline + new F7 test count; 0 F7-introduced regressions)
- [ ] Documentation updated:
  - [ ] `the_one/agents.md`: new convention citation(s); n=3 lift documented; `post-step-dispatcher-message-metadata-binding` updated to reference the lifted module
  - [ ] `the_one/connectors/README.md` (if exists) or inline docstrings: the `_inference.py` module documented; the new plugin hooks documented
  - [ ] `missions/11-discord-connector-depth/criterion-coverage.md`: row #12 marked `closed-by-F7`; row #13 marked `closed-by-F6+F7` (LLM-side projection added); `Last touched` column updated
  - [ ] **`missions/11-discord-connector-depth/mission.md` OQ3 resolution annotated**: the mission OQ3's original 4-mode set (`always-respond` / `mentioned-only` / `inference` / `never-respond`) collapsed to 2 modes (`mentioned-only` / `always-listening`) during F7 design; the OQ list entry annotated with the collapse rationale so the resolution trail is intelligible at mission-debrief time
- [ ] F6 flight debrief: Rec #4 (peer_name LLM-side surface) marked closed by F7
- [ ] M11 mission.md: F7 checkbox marked; Known Issues #2 + #3 (F2 + F3 pool/protocol questions) NOT in F7 scope — leave unchanged

### Verification

The flight succeeds when:

1. **Mentioned-only mode (default)**: a real-Discord multi-user channel test shows the bot responding only to `@mentions`, DMs, `/talk_to` overrides — and staying silent on all other channel chatter. Operator-side Chat UI does NOT show the silent inbound traffic. The `session_metadata["routing"]` audit log shows `disposition="policy-silent"` entries for the skipped turns.
2. **Always-listening mode (opt-in)**: with account toggle ON + agent toggle ON, the bot responds to `@mentions` AND to non-mentioned messages the inference call returns "yes" on — biased strongly toward "no". HAT verifies the inference's strict-default behavior with at least 10 borderline messages (a mix of clearly-engaging, clearly-not, and ambiguous); the inference correctly silences the clear-no's and the ambiguous's, engages on the clear-yes's.
3. **Operator-typed inference steering**: typing an operator-only message "next time someone says 'foo', respond with 'bar'" into the channel-attached session's Chat UI, then having a peer post "foo" in the channel → inference returns "yes" → agent engages with reply matching the steering.
4. **Channel-context tools**: an engaged agent can call `fetch_channel_history` / `fetch_thread_history` / `fetch_dm_history` / `list_visible_channels` and receive structured platform data; per-agent ACL is respected.
5. **LLM-side projection**: an agent receiving multi-user channel messages sees the inline-prefixed content in its LLM payload; operator-side Chat UI continues to render peer_name via F6 L4's left-aligned peer-bubble treatment; both representations are correct and aligned.
6. **Migration**: existing accounts with the old `auto_relay_platform_replies` key continue to function (read-only) until their first F7-era save, at which point the key is dropped and `always_listen` is defaulted False.
7. **System prompt accuracy** per `mechanical-fallback-prompt-truth-pairing`: the directive describes both the auto-relay invariant AND the policy gate's existence; no stale references to the deprecated OFF mode.
