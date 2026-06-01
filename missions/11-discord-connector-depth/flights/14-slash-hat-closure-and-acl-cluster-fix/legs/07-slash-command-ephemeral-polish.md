# Leg: slash-command-ephemeral-polish

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Make the 3 self-only slash commands (`/whoami`, `/agents`, `/help`) respond **ephemerally** (only the invoker sees them) while the 3 channel-affecting commands (`/talk_to`, `/new`, `/reset`) stay channel-visible. Closes M11 criterion #10's deferred "ephemeral where appropriate" sub-bullet. This is substrate work (interaction-followup plumbing), not a flag flip — per the flight DD.

## Context

- **Flight DD (operator-directed Phase 4, architect-cycle corrected)**: F13 L6 deferred the "ephemeral where appropriate" sub-bullet. The slash flow is `interaction.response.defer(ephemeral=True)` (`_discord.py:881`) → `dispatch_inbound` → `client.send(OutboundTarget, text)` (the dispatcher's built-in command-outbound site). There is no `interaction.response.send_message` to flip a flag on — the dispatcher posts via the normal channel `client.send`. To deliver an ephemeral reply, L7 threads the interaction-followup token to the outbound site so it can choose `interaction.followup.send(text, ephemeral=True)` vs a channel send.
- **Discord routing reality (FD recon)**: `DiscordPlugin.handle_command` returns `None` for all 6 commands (agents.md L9 narrative), so Discord slash invocations fall through to the dispatcher's **built-in** command-outbound site at `_inbound.py:719-744` (NOT the plugin site at `:700-716`). Both sites call `client.send(OutboundTarget(channel_id=…, thread_id=…), response.text)`. The built-in site is the load-bearing one for Discord; update BOTH for symmetry/future plugins.
- **Token threading + the CORRECT followup mechanism (design-review-verified against discord.py 2.4.0 — the original `Webhook.partial` plan was WRONG)**: carry the `interaction.token` STRING through `envelope.raw["interaction_followup_token"]` → the dispatcher copies it onto `OutboundTarget` → `DiscordClient.send` reconstructs an **application** webhook and sends ephemerally:
  ```python
  wh = discord.Webhook.from_state(
      data={"id": int(self._client.application_id), "type": 3, "token": token},
      state=self._client._connection,
  )
  await wh.send(content, ephemeral=True)   # type=3 (application) → ephemeral honored
  ```
  - **`discord.Webhook.partial(app_id, token).send(ephemeral=True)` does NOT work** — it builds a type=1 (incoming) webhook and `send(ephemeral=True)` raises `ValueError: ephemeral messages can only be sent from application webhooks`. Use `from_state` with `"type": 3` (verified to honor ephemeral).
  - **`application_id` source is `self._client.application_id`** (real `discord.Client` attr, populated at READY) — NOT the doctor REST path. It is `None` pre-READY → guard (see Edge Cases).
  - Why carry a token STRING (not the live interaction) on `OutboundTarget`: keeps `OutboundTarget` connector-agnostic (a plain string, not a live Discord object). The `from_state` + `self._client._connection` (private SDK attr) coupling lives INSIDE `DiscordClient` (the Discord adapter, which already reaches into `self._client` internals) — comment it. (Note: the original "keep `envelope.raw` JSON-serializable" rationale was moot — `_build_slash_envelope:229` already stashes a live `raw["discord_interaction"]` object, currently unused; leave it, it's pre-existing and out of scope. We add the token-string field rather than reuse that live object so the value crossing the connector-agnostic `OutboundTarget` boundary is a string.)
- **Current unconditional defer (`_discord.py:881`)**: `interaction.response.defer(ephemeral=True)` runs for ALL 6 commands → for the 3 channel-affecting commands the operator briefly sees an ephemeral "thinking…" ack and then a channel-visible reply (UX inconsistency). L7 makes the defer's `ephemeral` conditional on the command name.
- **`CommandResponse`** (`base.py:407`) is a `@dataclass(frozen=True, slots=True)` with just `text: str` — add `ephemeral: bool = False` (opt-in; existing/future handlers default to channel-visible, no behavior change).
- **Token-expiry guard**: interaction tokens are valid ~15 min from `defer`. Dispatcher outbound is typically sub-second, so this is defensive: if `followup.send` raises `discord.errors.NotFound` (token expired/invalid), fall back to channel `client.send` with a `[ephemeral fallback]` text prefix; catch + log the `NotFound` at INFO. No exception surfaces.

## Inputs

- `the_one/connectors/base.py` — `CommandResponse` (`:407`); `OutboundTarget` (`:133`).
- `the_one/connectors/_commands.py` — the 6 `_handle_*` handlers.
- `the_one/connectors/_inbound.py:700-744` — the two command-outbound sites (plugin `:700-716`, built-in `:719-744`).
- `the_one/connectors/_discord.py` — slash-body `_make_slash_body`/`_slash_command` (`:872-917`), the defer (`:881`), `_build_slash_envelope` (`:147+`, sets `envelope.raw`), `DiscordClient.send` (`:380+`), the bot's `application_id` (available on the client; cf `:1160`/`:1344`).
- `tests/test_connectors_commands.py` — per-command tests to extend + the new matrix test class.

## Outputs

- `CommandResponse.ephemeral: bool = False`; the 3 self-only handlers return `ephemeral=True`.
- `OutboundTarget` carries `interaction_followup_token: str | None = None` + `ephemeral: bool = False` (or equivalent), threaded from `envelope.raw`.
- Slash-body sets `envelope.raw["interaction_followup_token"] = interaction.token`; defer `ephemeral` is conditional on the command name.
- `DiscordClient.send` routes ephemeral followups vs channel sends, with token-expiry fallback.
- +4 dispatcher/outbound matrix tests.

## Acceptance Criteria

- [ ] `CommandResponse` gains an opt-in `ephemeral: bool = False`. `_handle_whoami`, `_handle_agents`, `_handle_help` return `CommandResponse(text=…, ephemeral=True)`; `_handle_talk_to`, `_handle_new`, `_handle_reset` return the default (`ephemeral=False`).
- [ ] `OutboundTarget` carries the followup token + ephemeral flag (e.g. `interaction_followup_token: str | None = None`, `ephemeral: bool = False`), defaulting so non-slash/non-ephemeral callers are unaffected.
- [ ] The slash-body sets `envelope.raw["interaction_followup_token"] = interaction.token` (via `_build_slash_envelope` or the slash-body); the conditional defer uses `ephemeral=True` ONLY for `{whoami, agents, help}` and `ephemeral=False` (public defer, or the appropriate public ack) for `{talk_to, new, reset}` — no more brief-ephemeral-then-channel inconsistency.
- [ ] Both dispatcher command-outbound sites (`_inbound.py:700-716` plugin + `:719-744` built-in) build the `OutboundTarget` with `ephemeral=response.ephemeral` and `interaction_followup_token=envelope.raw.get("interaction_followup_token")`.
- [ ] `DiscordClient.send`: when `target.ephemeral` AND `target.interaction_followup_token` truthy AND `self._client.application_id` is set → send via `discord.Webhook.from_state(data={"id": int(application_id), "type": 3, "token": token}, state=self._client._connection).send(content, ephemeral=True)`; otherwise the existing channel-send path. On `discord.errors.NotFound` (expired/invalid token, 404) OR `discord.errors.HTTPException` with `status == 401` → fall back to channel send with a `[ephemeral fallback]` prefix; caught + logged at INFO (no exception surfaces). The followup path returns a valid `SendResult` (ephemeral forces `wait=True` so a Message is returned → `platform_message_id=str(sent.id)`; set `details` to mark the path, e.g. `{"channel_type": "ephemeral_followup"}`).
- [ ] **+4 matrix tests at the `DiscordClient.send` level** (the branch site; the harness `_make_discord_client_with_sdk` at `tests/test_connectors_discord.py:1639` exists) covering the 4 cells of (`ephemeral` ∈ {True, False}) × (`interaction_followup_token` ∈ {present, absent}): ephemeral+token → followup path fired (channel-send NOT); the other 3 → channel path fired (followup NOT). **Patch the webhook construction** (`discord.Webhook.from_state`) / inject a followup recorder — do NOT make a real network send. Plus a thinner dispatcher-level assertion that both outbound sites pass the flags through (`ephemeral=response.ephemeral`, `interaction_followup_token=…raw.get(...)`). Plus the per-command tests: `/whoami`/`/agents`/`/help` assert `response.ephemeral is True`; `/talk_to`/`/new`/`/reset` assert `is False`. A unit test of the `NotFound`→fallback branch is welcome if cheap (the 15-min real token-expiry is verified end-to-end by L9's `slash-command-ephemeral-routing.md`).
- [ ] Backend suite: prior backend count **+4** (the matrix tests; per-command ephemeral assertions extend existing tests in place) / 0 errors. Record actuals.
- [ ] No backward-compat break: a handler that doesn't set `ephemeral` gets channel-visible (default `False`); a non-slash inbound (no token in raw) gets channel send.

## Verification Steps

- `docker exec the-one bash /app/scripts/run-tests.sh tests/test_connectors_commands.py tests/test_connectors_discord.py -x --timeout 30 -q` — new + extended tests pass.
- `docker exec the-one bash /app/scripts/run-tests.sh -m 'not browser and not live and not pixel' -q` — full backend at prior+4 / 0 errors (leg-end).
- `git grep -nE 'ephemeral=True' the_one/connectors/_discord.py the_one/connectors/_commands.py` — the 3 self-only commands' opt-in + the conditional defer.
- (Real ephemeral observability — `flags & 64` — is verified at L9/L10 via the behavior test, not here.)

## Implementation Guidance

1. **`CommandResponse.ephemeral`** (`base.py:407`): add `ephemeral: bool = False` to the frozen dataclass. Update the 3 self-only handlers in `_commands.py` to pass `ephemeral=True`; leave the channel-affecting 3 at default.
2. **`OutboundTarget`** (`base.py:133`): add `interaction_followup_token: str | None = None` and `ephemeral: bool = False` (defaults preserve all existing callers — the F4 platform-send tool, on_message replies, etc.).
3. **Slash-body** (`_discord.py`): set `envelope.raw["interaction_followup_token"] = interaction.token` (cleanest inside `_build_slash_envelope`, which already builds `raw`; pass the token in). Make the defer conditional: hardcode the self-only set `{"whoami","agents","help"}` in the slash-body for `defer(ephemeral=…)` (the handler owns the response-ephemeral via CommandResponse; the slash-body owns the ack-ephemeral — both keyed on the command name; note the deliberate coupling in a comment). For the channel-affecting set, defer with `ephemeral=False` (a public "thinking…" ack) so there's no ephemeral-then-channel flip.
4. **Dispatcher outbound** (`_inbound.py` both sites): build `OutboundTarget(channel_id=…, thread_id=…, ephemeral=response.ephemeral, interaction_followup_token=working_envelope.raw.get("interaction_followup_token"))`.
5. **`DiscordClient.send`** (`_discord.py:380+`): at the top, `if target.ephemeral and target.interaction_followup_token and self._client.application_id:` → reconstruct the application webhook via `discord.Webhook.from_state(data={"id": int(self._client.application_id), "type": 3, "token": target.interaction_followup_token}, state=self._client._connection)` and `await wh.send(content, ephemeral=True)`; return a `SendResult` with `platform_message_id=str(sent.id)` + `details={"channel_type": "ephemeral_followup"}`. Wrap the followup send in try/except `discord.errors.NotFound` (and `discord.errors.HTTPException` with `status == 401`) → log INFO + fall through to the channel path with `content = "[ephemeral fallback] " + content`. **Do NOT use `Webhook.partial`** (type=1 → `ValueError` on `ephemeral=True`). Add a comment noting the `self._client._connection` private-attr coupling (acceptable inside the Discord adapter). Otherwise (no token / not ephemeral / `application_id` None) → the existing channel-resolution ladder unchanged, with its existing Forbidden/NotFound/429 error-mapping.
6. **Tests**: extend the per-command tests for the ephemeral assertions; add `TestDispatcherOutboundRoutesEphemeral` with a mock `DiscordClient` (or a mock client exposing both a channel-send recorder and a followup recorder) covering the 4 cells. If a `DiscordClient.send`-level test is cleaner for the routing branch, put the 4 cells there and keep the dispatcher test to "passes the flags through correctly."
7. **Run via the wrapper**; record counts.

## Edge Cases

- **`application_id` is `None`** (pre-READY): the `if … and self._client.application_id` guard fails → channel send + WARNING. This would leak a self-only command (e.g. `/whoami`) into the channel — but it's a near-impossible window: slash commands aren't invokable until the gateway is READY (which is when `application_id` populates), so in practice `application_id` is always set when a slash arrives. Accept the channel-leak-on-pre-READY trade-off with a WARNING log (don't crash, don't queue).
- **`talk_to` vs `talk-to` spelling**: the slash vocab uses `talk_to` (underscore); `COMMAND_HANDLERS` keys on `talk-to` (hyphen, F7 parser normalizes). The 3 ephemeral commands (`whoami`/`agents`/`help`) spell identically in both, so no L7 bug — but the handler-ephemeral set (keyed on parsed command name) and the defer set (keyed on slash `name`) are independently name-keyed; note this coupling in a comment.
- **Non-slash command inbound** (text-prefix `/agents` typed as a message, no interaction token): `envelope.raw` has no `interaction_followup_token` → channel send, even though `response.ephemeral is True`. That's correct — there's no interaction to make it ephemeral on. (Note this in a comment; the ephemeral intent is best-effort, gated on having an interaction.)
- **`ephemeral=True` but token expired** (>15 min): `NotFound` → `[ephemeral fallback]` channel send. Defensive only.
- **DM-invoked self-only command**: an ephemeral followup in a DM is fine (Discord allows it); if the followup path errors in a DM context, the channel-send fallback covers it.

## Files Affected

- `the_one/connectors/base.py` — `CommandResponse.ephemeral`; `OutboundTarget` token + ephemeral fields.
- `the_one/connectors/_commands.py` — 3 self-only handlers return `ephemeral=True`.
- `the_one/connectors/_inbound.py` — both command-outbound sites pass the flags.
- `the_one/connectors/_discord.py` — `_build_slash_envelope` sets the token in raw; conditional defer; `DiscordClient.send` ephemeral-followup branch + token-expiry fallback.
- `tests/test_connectors_commands.py` (+ possibly `tests/test_connectors_discord.py`) — +4 matrix tests + per-command ephemeral assertions.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] All acceptance criteria verified (4 matrix cells + per-command ephemeral flags + token-expiry fallback)
- [ ] Backend at prior+4 / 0 errors (wrapper used; actual count recorded)
- [ ] No backward-compat break (defaults preserve existing callers)
- [ ] Update flight-log.md with L7 leg progress entry (design realized, test counts, any discord.py-idiom notes)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)
